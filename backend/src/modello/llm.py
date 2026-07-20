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
- `crea_cascata`: fallback sul modello successivo. STICKY solo per le cause
  PERSISTENTI (quota, modello assente: `CODICI_STICKY`), cosi' un modello esaurito
  non viene ri-provato per ogni articolo. Per le cause transitorie (rete, 5xx,
  risposta non JSON) il ripiego vale solo per la chiamata in corso: il modello
  migliore non va perso per tutta la run a causa di un singolo inciampo.

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

# Cause per cui il declassamento e' PERSISTENTE (sticky) per il resto della run:
# descrivono uno stato del modello che non cambia a breve — quota esaurita (429),
# ID inesistente o non valido (400/404), richiesta oltre il tetto TPM di QUEL
# modello (413), conflitto (409). Qui ri-provare a ogni articolo e' solo spreco.
#
# Tutto il resto (5xx, timeout, errori di rete, RispostaNonJSON) e' TRANSITORIO:
# il modello e' sano, ha solo inciampato su una risposta. Si ripiega per la
# singola chiamata e la successiva riparte dal modello migliore. Prima non era
# cosi' e una sola risposta malformata declassava il primario per l'intera run:
# il 2026-07-20 il 70b ha fatto 9 chiamate su 111, con 60 finite sull'8b (sez. 17).
CODICI_STICKY = frozenset({400, 404, 409, 413, 429})

# Una risposta non-JSON si ritenta sullo STESSO modello prima di ripiegare:
# l'output di un LLM e' stocastico, e ri-chiedere spesso basta. Nessuna attesa tra
# i tentativi — non e' un problema di rate, e' un campionamento sfortunato.
RETRY_TENTATIVI_JSON = 2

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


def _motivo(e: Exception) -> str:
    """Descrizione leggibile della causa, per i log.

    Serve a distinguere casi che prima finivano tutti in un indistinguibile
    "HTTP None": una risposta malformata e un timeout di rete hanno rimedi
    diversi, e il log era l'unico modo per accorgersene a run finita.
    """
    if isinstance(e, RispostaNonJSON):
        # `_estrai_json` mette gia' nel messaggio i primi 200 caratteri della
        # risposta: riportarli e' l'unico modo per sapere COSA scrive il modello
        # invece di dedurlo. Senza, ogni causa diversa (testo libero, risposta
        # vuota, JSON troncato) si legge uguale nei log.
        return f"risposta non JSON — {e}"
    codice = _codice_errore(e)
    if codice is not None:
        return f"HTTP {codice}"
    if _e_errore_rete(e):
        return f"errore di rete ({e.__class__.__name__})"
    return e.__class__.__name__


def _esegui_con_retry(chiamata: Callable[[], dict]) -> dict:
    """Esegue `chiamata` ritentando sui transitori dello stesso modello.

    Backoff esponenziale con jitter su 5xx/timeout. Una `RispostaNonJSON` si
    ritenta anch'essa (l'output del modello e' stocastico: ri-chiedere spesso
    basta) ma SENZA attesa e con meno tentativi, perche' non e' un problema di
    rate. Gli altri errori e l'ultimo tentativo fallito si ri-sollevano.
    """
    ultimo: Exception | None = None
    for tentativo in range(RETRY_TENTATIVI):
        try:
            return chiamata()
        except Exception as e:  # noqa: BLE001 - si ri-solleva se non ritentabile
            ultimo = e
            non_json = isinstance(e, RispostaNonJSON)
            limite = RETRY_TENTATIVI_JSON if non_json else RETRY_TENTATIVI
            ritentabile = non_json or _codice_errore(e) in CODICI_RETRY or _e_errore_rete(e)
            if not ritentabile or tentativo >= limite - 1:
                raise
            if not non_json:
                time.sleep(RETRY_ATTESA_BASE * (2 ** tentativo) + random.uniform(0, 1))
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
                # Sticky SOLO se la causa descrive uno stato persistente del
                # modello (quota, ID morto): un inciampo transitorio non deve
                # costare l'uso del modello migliore per tutto il resto della run.
                persistente = _codice_errore(e) in CODICI_STICKY
                coda = ("passo stabilmente a" if persistente
                        else "ripiego solo per questa chiamata su")
                print(
                    f"[attenzione] modello '{modelli[i]}' ha fallito "
                    f"({_motivo(e)}): {coda} '{modelli[i + 1]}'",
                    file=sys.stderr,
                )
                i += 1
                if persistente:
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
        scelta = risposta.choices[0]
        contenuto = scelta.message.content or ""
        try:
            return _estrai_json(contenuto)
        except RispostaNonJSON as e:
            # Il perche' di un JSON illeggibile cambia il rimedio: 'length' vuol
            # dire risposta TRONCATA (serve piu' spazio o un prompt piu' corto),
            # 'stop' vuol dire che il modello ha ignorato il formato (serve
            # response_format). A log erano indistinguibili.
            motivo = getattr(scelta, "finish_reason", None)
            raise RispostaNonJSON(
                f"{e} [finish_reason={motivo}, {len(contenuto)} caratteri]"
            ) from e

    # cascata sticky (fallback tra modelli) con retry backoff sui 5xx del modello
    # corrente; il 429 (quota) fa cambiare modello subito, senza attese.
    return crea_cascata(
        modelli, lambda m, prompt: _esegui_con_retry(lambda: _chiama(m, prompt))
    )
