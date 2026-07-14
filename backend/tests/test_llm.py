"""Robustezza dell'adattatore LLM (src/modello/llm.py): parsing JSON, retry sui
transitori e cascata sticky di modelli (Groq).

I modelli spesso avvolgono il JSON in un blocco markdown o aggiungono testo:
`_estrai_json` recupera comunque il primo oggetto JSON (fix "Extra data").
"""
import pytest

from src.modello import llm
from src.modello.llm import (
    RispostaNonJSON,
    _codice_errore,
    _esegui_con_retry,
    _estrai_json,
    crea_cascata,
)


class _ErroreHTTP(Exception):
    """Finto errore SDK con un codice HTTP, come APIStatusError di openai."""

    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.status_code = code


def test_json_puro():
    assert _estrai_json('{"sintesi": "a", "perche_conta": "b"}') == {
        "sintesi": "a",
        "perche_conta": "b",
    }


def test_fence_markdown():
    testo = '```json\n{"sintesi": "a"}\n```'
    assert _estrai_json(testo) == {"sintesi": "a"}


def test_testo_dopo_oggetto():
    # e' il caso reale che dava "Extra data: line 6 column 1"
    assert _estrai_json('{"sintesi": "a"}\nEcco la spiegazione.') == {"sintesi": "a"}


def test_testo_prima_oggetto():
    assert _estrai_json('Certo, ecco:\n{"sintesi": "a"}') == {"sintesi": "a"}


def test_risposta_vuota():
    with pytest.raises(ValueError):
        _estrai_json("")


def test_senza_json():
    with pytest.raises(ValueError):
        _estrai_json("nessun json qui")


# --- retry sugli errori transitori -----------------------------------------

@pytest.fixture(autouse=True)
def _niente_sleep(monkeypatch):
    # niente attese reali nei test del backoff
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)


def test_codice_errore():
    assert _codice_errore(_ErroreHTTP(503)) == 503
    assert _codice_errore(ValueError("boh")) is None


def test_retry_recupera_dopo_503():
    tentativi = {"n": 0}

    def chiamata():
        tentativi["n"] += 1
        if tentativi["n"] < 3:
            raise _ErroreHTTP(503)  # sovraccarico temporaneo
        return {"sintesi": "ok"}

    assert _esegui_con_retry(chiamata) == {"sintesi": "ok"}
    assert tentativi["n"] == 3  # ha ritentato fino al successo


def test_retry_non_ritenta_errore_client():
    tentativi = {"n": 0}

    def chiamata():
        tentativi["n"] += 1
        raise _ErroreHTTP(400)  # errore non transitorio: subito rilanciato

    with pytest.raises(_ErroreHTTP):
        _esegui_con_retry(chiamata)
    assert tentativi["n"] == 1


def test_retry_si_arrende_dopo_max_tentativi():
    tentativi = {"n": 0}

    def chiamata():
        tentativi["n"] += 1
        raise _ErroreHTTP(503)

    with pytest.raises(_ErroreHTTP):
        _esegui_con_retry(chiamata)
    assert tentativi["n"] == llm.RETRY_TENTATIVI


def test_retry_non_ritenta_quota_429():
    # il 429 (quota) non si libera a breve: nessun backoff, si rilancia subito
    # per far cambiare modello alla cascata.
    tentativi = {"n": 0}

    def chiamata():
        tentativi["n"] += 1
        raise _ErroreHTTP(429)

    with pytest.raises(_ErroreHTTP):
        _esegui_con_retry(chiamata)
    assert tentativi["n"] == 1


# --- cascata sticky di modelli ---------------------------------------------

def test_cascata_passa_al_modello_successivo_su_quota():
    usati = []

    def esegui(modello, _prompt):
        usati.append(modello)
        if modello == "primario":
            raise _ErroreHTTP(429)  # quota esaurita sul primario
        return {"sintesi": f"ok da {modello}"}

    genera = crea_cascata(["primario", "ripiego"], esegui)
    assert genera("p") == {"sintesi": "ok da ripiego"}
    assert usati == ["primario", "ripiego"]  # provati in ordine


def test_cascata_sticky_non_riprova_il_modello_morto():
    # il cuore del fix "va in loop": dopo che il primario e' risultato esaurito,
    # gli articoli successivi NON lo ri-provano piu'.
    usati = []

    def esegui(modello, _prompt):
        usati.append(modello)
        if modello == "primario":
            raise _ErroreHTTP(429)
        return {"sintesi": "ok"}

    genera = crea_cascata(["primario", "ripiego"], esegui)
    genera("articolo-1")  # qui scopre che il primario e' morto e passa a ripiego
    genera("articolo-2")  # deve andare DIRETTO al ripiego
    genera("articolo-3")
    # il primario e' stato toccato una sola volta in tutto
    assert usati == ["primario", "ripiego", "ripiego", "ripiego"]


def test_cascata_non_scatta_su_errore_fatale_auth():
    # 401 (chiave errata) e' fatale e uguale per tutti i modelli: nessun ripiego.
    usati = []

    def esegui(modello, _prompt):
        usati.append(modello)
        raise _ErroreHTTP(401)

    with pytest.raises(_ErroreHTTP):
        crea_cascata(["primario", "ripiego"], esegui)("p")
    assert usati == ["primario"]  # non ha provato il ripiego


def test_cascata_cambia_modello_su_id_non_valido_400():
    # un ID modello stantio/non valido (400/404) non deve fermare la run: si passa
    # al modello successivo.
    usati = []

    def esegui(modello, _prompt):
        usati.append(modello)
        if modello == "id-stantio":
            raise _ErroreHTTP(400)
        return {"sintesi": "ok"}

    genera = crea_cascata(["id-stantio", "valido"], esegui)
    assert genera("p") == {"sintesi": "ok"}
    assert usati == ["id-stantio", "valido"]


def test_cascata_solleva_se_tutti_i_modelli_falliscono():
    def esegui(modello, _prompt):
        raise _ErroreHTTP(503)

    with pytest.raises(_ErroreHTTP):
        crea_cascata(["a", "b"], esegui)("p")


def test_cascata_primo_modello_ok_non_usa_ripieghi():
    usati = []

    def esegui(modello, _prompt):
        usati.append(modello)
        return {"sintesi": "subito ok"}

    assert crea_cascata(["a", "b"], esegui)("p") == {"sintesi": "subito ok"}
    assert usati == ["a"]


# --- errori di rete (senza codice HTTP) ------------------------------------

class APITimeoutError(Exception):
    """Nome-classe come l'errore di timeout dell'SDK openai (nessun codice)."""


def test_retry_ritenta_su_timeout_di_rete():
    tentativi = {"n": 0}

    def chiamata():
        tentativi["n"] += 1
        if tentativi["n"] < 2:
            raise APITimeoutError("timeout")
        return {"sintesi": "ok"}

    assert _esegui_con_retry(chiamata) == {"sintesi": "ok"}
    assert tentativi["n"] == 2


def test_cascata_cambia_modello_su_errore_di_rete():
    def esegui(modello, _prompt):
        if modello == "a":
            raise APITimeoutError("connection reset")
        return {"sintesi": "ok"}

    assert crea_cascata(["a", "b"], esegui)("p") == {"sintesi": "ok"}


# --- risposta non-JSON: cambia modello, non ferma la run -------------------

def test_estrai_json_malformato_solleva_risposta_non_json():
    with pytest.raises(RispostaNonJSON):
        _estrai_json("We need to produce JSON and then...")  # nessuna graffa
    with pytest.raises(RispostaNonJSON):
        _estrai_json('{"sintesi": }')  # graffa ma JSON rotto


def test_cascata_cambia_modello_su_risposta_non_json():
    # un modello 'reasoning' che restituisce testo libero non deve fermare la run:
    # si passa al modello successivo.
    usati = []

    def esegui(modello, _prompt):
        usati.append(modello)
        if modello == "chiacchierone":
            raise RispostaNonJSON("We need to produce JSON...")
        return {"sintesi": "ok"}

    genera = crea_cascata(["chiacchierone", "serio"], esegui)
    assert genera("p") == {"sintesi": "ok"}
    assert usati == ["chiacchierone", "serio"]
