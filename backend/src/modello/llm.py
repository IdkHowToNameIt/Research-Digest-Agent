"""Adattatore LLM per la sintesi finale, via Groq (API OpenAI-compatibile).

Espone `crea_generatore()` -> `genera(prompt: str) -> dict`. Il resto della
pipeline dipende solo da questa callable, cosi' nei test si inietta un finto
generatore senza rete ne' API key.

Perche' Groq: una sola chiave (`GROQ_API_KEY`) con un free tier molto ampio
(~migliaia di richieste/giorno per modello), sufficiente e con margine per la run
settimanale — a differenza del tetto giornaliero d'account di OpenRouter, che si
esauriva. I modelli restano in CASCATA come rete di sicurezza: se un modello
esaurisce la quota (429) o viene deprecato (400/404/5xx) si passa al successivo,
cosi' la run settimanale non si ferma.

Resilienza a due livelli (una singola chiamata KO non deve fermare la run, che
sintetizza gli articoli uno alla volta):
- `_esegui_con_retry`: retry con backoff sui transitori (5xx/timeout) dello STESSO
  modello (assorbe i picchi momentanei);
- `crea_cascata`: fallback STICKY sul modello successivo per quota/modello-assente
  (l'indice avanza in modo persistente: un modello esaurito non viene ri-provato
  per ogni articolo).

Il formato JSON dell'output ({"sintesi","perche_conta","note"}) e' istruito dal
prompt (prompts.py) e letto in modo tollerante da `_estrai_json`: non serve lo
structured-output di un singolo provider, cosi' i modelli sono intercambiabili.

L'import di `openai` e' pigro: la libreria serve solo in modalita' reale.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from typing import Callable, Sequence, TypedDict

# Modello primario + cascata di ripiego: ID Groq, instruct e multilingue (adatti
# alla sintesi in italiano). Aggiornabili dalla lista live:
#   curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY" | jq -r '.data[].id'
MODELLO_DEFAULT = "llama-3.3-70b-versatile"
MODELLI_FALLBACK_DEFAULT = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "gemma2-9b-it",
    "llama-3.1-8b-instant",
)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Errori che fanno passare al modello SUCCESSIVO nella cascata: quota (429),
# richiesta troppo grande per il limite TPM del modello (413: il tetto
# token/minuto varia per modello, un altro puo' accettarla), modello assente/non
# valido (400/404), server KO (5xx). Auth (401/403) NO: e' fatale e uguale per
# tutti i modelli, inutile ciclare.
CODICI_CAMBIA_MODELLO = frozenset({400, 404, 408, 409, 413, 429, 500, 502, 503, 504})
# Sottoinsieme su cui conviene ritentare lo STESSO modello con backoff (picchi
# temporanei). Il 429 (quota) e' escluso: non si libera a breve, meglio cambiare
# modello subito invece di sprecare attese.
CODICI_RETRY = frozenset({408, 500, 502, 503, 504})
RETRY_TENTATIVI = 3
RETRY_ATTESA_BASE = 2.0  # secondi (backoff esponenziale: 2, 4, 8, ...)

Generatore = Callable[[str], dict]


class _SchemaSintesi(TypedDict):
    """Chiavi attese nella risposta del modello (documentazione/forma)."""

    sintesi: str
    perche_conta: str
    note: str


class LLMNonConfigurato(RuntimeError):
    """Sollevata quando manca la API key per la modalita' con modello."""


class RispostaNonJSON(ValueError):
    """Il modello non ha restituito un oggetto JSON valido.

    Trattata dalla cascata come motivo per passare al modello successivo: alcuni
    modelli (spec. 'reasoning') ignorano l'istruzione di formato e producono testo
    libero. Sottoclasse di ValueError per retro-compatibilita' nei test.
    """


def _estrai_json(testo: str) -> dict:
    """Estrae il primo oggetto JSON dalla risposta del modello.

    I modelli spesso avvolgono il JSON in un blocco markdown (```json ... ```) o
    aggiungono testo attorno: json.loads fallirebbe con "Extra data". Qui si cerca
    la prima graffa e si usa raw_decode, che legge un solo valore JSON e ignora
    cio' che segue. Se non c'e' JSON valido -> RispostaNonJSON (cascata cambia
    modello).
    """
    if not testo:
        raise RispostaNonJSON("risposta vuota dal modello")
    inizio = testo.find("{")
    if inizio == -1:
        raise RispostaNonJSON(f"nessun oggetto JSON nella risposta: {testo[:200]!r}")
    try:
        oggetto, _ = json.JSONDecoder().raw_decode(testo[inizio:])
    except json.JSONDecodeError as e:
        raise RispostaNonJSON(f"JSON malformato nella risposta: {testo[:200]!r}") from e
    return oggetto


def _leggi_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise LLMNonConfigurato(
            "Manca la API key di Groq: imposta GROQ_API_KEY (in locale nel file "
            ".env, in produzione come secret di GitHub Actions). Creane una gratis "
            "su https://console.groq.com/keys."
        )
    return key


def _codice_errore(e: Exception) -> int | None:
    """Codice HTTP di un errore dell'SDK, se presente (openai: `status_code`)."""
    for attr in ("status_code", "code"):
        val = getattr(e, attr, None)
        if isinstance(val, int):
            return val
    return None


def _e_errore_rete(e: Exception) -> bool:
    """True per errori di connessione/timeout (senza codice HTTP)."""
    nome = e.__class__.__name__
    return "Timeout" in nome or "Connection" in nome


def _esegui_con_retry(chiamata: Callable[[], dict]) -> dict:
    """Esegue `chiamata` ritentando sui transitori dello stesso modello.

    Backoff esponenziale con jitter su 5xx/timeout; gli altri errori e l'ultimo
    tentativo fallito vengono ri-sollevati subito.
    """
    ultimo: Exception | None = None
    for tentativo in range(RETRY_TENTATIVI):
        try:
            return chiamata()
        except Exception as e:  # noqa: BLE001 - si ri-solleva se non ritentabile
            ultimo = e
            ritentabile = _codice_errore(e) in CODICI_RETRY or _e_errore_rete(e)
            if not ritentabile or tentativo == RETRY_TENTATIVI - 1:
                raise
            attesa = RETRY_ATTESA_BASE * (2 ** tentativo) + random.uniform(0, 1)
            time.sleep(attesa)
    raise ultimo  # pragma: no cover - il loop ritorna o solleva prima


def crea_cascata(
    modelli: Sequence[str], esegui: Callable[[str, str], dict]
) -> Callable[[str], dict]:
    """Cascata STICKY di modelli: ritorna una funzione `prompt -> dict`.

    Prova `esegui(modello, prompt)` partendo dal modello corrente e ripiega sul
    successivo su errori quota/modello-assente/server (CODICI_CAMBIA_MODELLO). Il
    passaggio e' *sticky*: l'indice del modello avanza in modo persistente tra
    chiamate diverse, cosi' un modello esaurito viene abbandonato UNA volta e non
    ri-provato per ogni articolo. Gli errori fatali (es. 401/403 auth) e il
    fallimento dell'ultimo modello si ri-sollevano.

    Nessun reset entro la run: la quota free non si libera a breve. Il prossimo
    run settimanale ricrea il generatore e riparte dal primario.
    """
    stato = {"idx": 0}

    def esegui_cascata(prompt: str) -> dict:
        ultimo: Exception | None = None
        i = stato["idx"]
        while i < len(modelli):
            try:
                return esegui(modelli[i], prompt)
            except Exception as e:  # noqa: BLE001 - si ri-solleva se non recuperabile
                ultimo = e
                cambiabile = (
                    isinstance(e, RispostaNonJSON)
                    or _codice_errore(e) in CODICI_CAMBIA_MODELLO
                    or _e_errore_rete(e)
                )
                if not cambiabile or i == len(modelli) - 1:
                    raise
                print(
                    f"[attenzione] modello '{modelli[i]}' non disponibile "
                    f"(HTTP {_codice_errore(e)}): passo stabilmente a "
                    f"'{modelli[i + 1]}' per il resto della run",
                    file=sys.stderr,
                )
                i += 1
                stato["idx"] = i  # sticky: non si torna piu' indietro
        raise ultimo  # pragma: no cover - il loop ritorna o solleva prima

    return esegui_cascata


def crea_generatore(
    api_key: str | None = None,
    model: str = MODELLO_DEFAULT,
    modelli_fallback: Sequence[str] | None = None,
    on_uso: Callable[[str, int, int], None] | None = None,
) -> Generatore:
    """Crea la callable di generazione (Groq, JSON via prompt).

    `on_uso(modello, prompt_tokens, completion_tokens)` — se fornita — viene
    chiamata dopo ogni risposta riuscita del modello, per contabilizzare l'uso di
    token (metriche/costo). È volutamente una callback e non un import diretto, per
    non far dipendere questo adattatore dal modulo delle metriche.
    """
    key = _leggi_api_key(api_key)
    fallback = MODELLI_FALLBACK_DEFAULT if modelli_fallback is None else tuple(modelli_fallback)
    # primario + ripieghi, senza duplicati e preservando l'ordine
    modelli: list[str] = list(dict.fromkeys([model, *fallback]))
    from openai import OpenAI  # import pigro: richiesto solo in modalita' reale

    client = OpenAI(base_url=GROQ_BASE_URL, api_key=key)

    def _chiama(modello: str, prompt: str) -> dict:
        risposta = client.chat.completions.create(
            model=modello,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        uso = getattr(risposta, "usage", None)
        if on_uso is not None and uso is not None:
            on_uso(
                modello,
                getattr(uso, "prompt_tokens", 0) or 0,
                getattr(uso, "completion_tokens", 0) or 0,
            )
        return _estrai_json(risposta.choices[0].message.content or "")

    # cascata sticky (fallback tra modelli) con retry backoff sui 5xx del modello
    # corrente; il 429 (quota) fa cambiare modello subito, senza attese.
    return crea_cascata(
        modelli, lambda m, prompt: _esegui_con_retry(lambda: _chiama(m, prompt))
    )
