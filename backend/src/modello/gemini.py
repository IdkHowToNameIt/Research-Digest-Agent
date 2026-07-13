"""Adattatore per il modello Gemini (usato SOLO per la sintesi finale).

Espone una factory `crea_generatore()` che restituisce una funzione
`genera(prompt: str) -> dict`. Il resto della pipeline dipende solo da questa
callable, cosi' nei test si inietta un finto generatore senza rete ne' API key.

L'import di `google.genai` e' pigro: la libreria serve solo in modalita' reale.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from typing import Callable, Sequence, TypedDict

MODELLO_DEFAULT = "gemini-2.5-flash"
# Modelli di ripiego se il primario esaurisce quota/e' sovraccarico: hanno un
# bucket di quota separato. Ordinati dal piu' capiente. Sovrascrivibili da config
# (`modelli_fallback`). Alias -latest per non incorrere nei modelli dismessi.
MODELLI_FALLBACK_DEFAULT = ("gemini-flash-lite-latest", "gemini-2.0-flash")

# Errori HTTP transitori (sovraccarico/limiti) su cui vale la pena ritentare.
CODICI_TRANSITORI = frozenset({429, 500, 502, 503, 504})
RETRY_TENTATIVI = 5
RETRY_ATTESA_BASE = 2.0  # secondi (backoff esponenziale: 2, 4, 8, ...)

Generatore = Callable[[str], dict]


class _SchemaSintesi(TypedDict):
    """Schema di output passato a Gemini (response_schema).

    Vincola la generazione a JSON valido con esattamente questi campi: senza
    schema il modello puo' produrre JSON malformato (virgolette non escapate nel
    testo -> JSONDecodeError). `note` e' sempre presente ma puo' essere "".
    """

    sintesi: str
    perche_conta: str
    note: str


class GeminiNonConfigurato(RuntimeError):
    """Sollevata quando manca la API key per la modalita' con modello."""


def _estrai_json(testo: str) -> dict:
    """Estrae il primo oggetto JSON dalla risposta del modello.

    Anche con response_mime_type=application/json alcuni modelli avvolgono il
    JSON in un blocco markdown (```json ... ```) o aggiungono testo dopo
    l'oggetto: json.loads fallirebbe con "Extra data". Qui si cerca la prima
    graffa e si usa raw_decode, che legge un solo valore JSON e ignora tutto
    cio' che segue.
    """
    if not testo:
        raise ValueError("risposta vuota dal modello")
    inizio = testo.find("{")
    if inizio == -1:
        raise ValueError(f"nessun oggetto JSON nella risposta: {testo[:200]!r}")
    oggetto, _ = json.JSONDecoder().raw_decode(testo[inizio:])
    return oggetto


def _leggi_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise GeminiNonConfigurato(
            "Manca la API key di Gemini: imposta GEMINI_API_KEY (in locale nel file "
            ".env, in produzione come secret di GitHub Actions)."
        )
    return key


def _codice_errore(e: Exception) -> int | None:
    """Codice HTTP di un errore dell'SDK Gemini, se presente."""
    for attr in ("code", "status_code"):
        val = getattr(e, attr, None)
        if isinstance(val, int):
            return val
    return None


def _esegui_con_retry(chiamata: Callable[[], dict]) -> dict:
    """Esegue `chiamata` ritentando sugli errori HTTP transitori.

    Backoff esponenziale con jitter; gli errori non transitori (es. 400/404) e
    l'ultimo tentativo fallito vengono ri-sollevati subito.
    """
    ultimo: Exception | None = None
    for tentativo in range(RETRY_TENTATIVI):
        try:
            return chiamata()
        except Exception as e:  # noqa: BLE001 - si ri-solleva se non transitorio
            ultimo = e
            if _codice_errore(e) not in CODICI_TRANSITORI or tentativo == RETRY_TENTATIVI - 1:
                raise
            attesa = RETRY_ATTESA_BASE * (2 ** tentativo) + random.uniform(0, 1)
            time.sleep(attesa)
    raise ultimo  # pragma: no cover - il loop ritorna o solleva prima


def _genera_con_fallback(modelli: Sequence[str], esegui: Callable[[str], dict]) -> dict:
    """Prova `esegui(modello)` sui modelli in ordine, ripiegando sul successivo.

    Si passa al modello dopo SOLO su errori transitori/quota (429/5xx): se il
    primario esaurisce la quota o e' sovraccarico, un altro modello (bucket di
    quota separato) evita di fermare la run. Gli errori non transitori (400/404)
    e il fallimento dell'ultimo modello vengono ri-sollevati.
    """
    ultimo: Exception | None = None
    for i, modello in enumerate(modelli):
        try:
            return esegui(modello)
        except Exception as e:  # noqa: BLE001 - si ri-solleva se non recuperabile
            ultimo = e
            ultimo_modello = i == len(modelli) - 1
            if _codice_errore(e) not in CODICI_TRANSITORI or ultimo_modello:
                raise
            print(
                f"[attenzione] modello '{modello}' non disponibile "
                f"(HTTP {_codice_errore(e)}): ripiego su '{modelli[i + 1]}'",
                file=sys.stderr,
            )
    raise ultimo  # pragma: no cover - il loop ritorna o solleva prima


def crea_generatore(
    api_key: str | None = None,
    model: str = MODELLO_DEFAULT,
    modelli_fallback: Sequence[str] | None = None,
) -> Generatore:
    """Crea la callable di generazione basata su Gemini (structured JSON).

    Due livelli di resilienza, cosi' un intoppo di Gemini non ferma la run
    settimanale (che sintetizza gli articoli uno alla volta):
    - retry con backoff esponenziale sui picchi transitori dello STESSO modello;
    - fallback su un ALTRO modello (quota separata) se il primario resta
      non disponibile per quota/sovraccarico.
    """
    key = _leggi_api_key(api_key)
    fallback = MODELLI_FALLBACK_DEFAULT if modelli_fallback is None else tuple(modelli_fallback)
    # primario + ripieghi, senza duplicati e preservando l'ordine
    modelli: list[str] = list(dict.fromkeys([model, *fallback]))
    from google import genai  # import pigro: richiesto solo in modalita' reale

    client = genai.Client(api_key=key)

    def _chiama(modello: str, prompt: str) -> dict:
        risposta = client.models.generate_content(
            model=modello,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                # constrained decoding: garantisce JSON valido con questi campi
                "response_schema": _SchemaSintesi,
            },
        )
        return _estrai_json(risposta.text)

    def genera(prompt: str) -> dict:
        return _genera_con_fallback(
            modelli, lambda m: _esegui_con_retry(lambda: _chiama(m, prompt))
        )

    return genera
