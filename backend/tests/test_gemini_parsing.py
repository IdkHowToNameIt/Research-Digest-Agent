"""Robustezza del parsing JSON della risposta Gemini (src/modello/gemini.py).

I modelli, anche con response_mime_type=application/json, a volte avvolgono
l'oggetto in un blocco markdown o aggiungono testo: `_estrai_json` deve
recuperare comunque il primo oggetto JSON (fix "Extra data" di json.loads).
"""
import pytest

from src.modello.gemini import _estrai_json


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
