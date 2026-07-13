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
import time
from typing import Callable, TypedDict

MODELLO_DEFAULT = "gemini-2.5-flash"

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


def crea_generatore(api_key: str | None = None, model: str = MODELLO_DEFAULT) -> Generatore:
    """Crea la callable di generazione basata su Gemini (structured JSON).

    La chiamata e' protetta da retry con backoff esponenziale sugli errori
    transitori (503 "high demand", 429 rate limit, 5xx): un picco momentaneo di
    Gemini non deve far fallire l'intera run settimanale, che sintetizza gli
    articoli uno alla volta.
    """
    key = _leggi_api_key(api_key)
    from google import genai  # import pigro: richiesto solo in modalita' reale

    client = genai.Client(api_key=key)

    def _chiama(prompt: str) -> dict:
        risposta = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                # constrained decoding: garantisce JSON valido con questi campi
                "response_schema": _SchemaSintesi,
            },
        )
        return _estrai_json(risposta.text)

    def genera(prompt: str) -> dict:
        return _esegui_con_retry(lambda: _chiama(prompt))

    return genera
