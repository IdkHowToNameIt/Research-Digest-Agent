"""Robustezza del parsing JSON della risposta Gemini (src/modello/gemini.py).

I modelli, anche con response_mime_type=application/json, a volte avvolgono
l'oggetto in un blocco markdown o aggiungono testo: `_estrai_json` deve
recuperare comunque il primo oggetto JSON (fix "Extra data" di json.loads).
"""
import pytest

from src.modello import gemini
from src.modello.gemini import _codice_errore, _esegui_con_retry, _estrai_json


class _ErroreHTTP(Exception):
    """Finto errore SDK con un codice HTTP, come APIError di google-genai."""

    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


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
    monkeypatch.setattr(gemini.time, "sleep", lambda _s: None)


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
    assert tentativi["n"] == gemini.RETRY_TENTATIVI
