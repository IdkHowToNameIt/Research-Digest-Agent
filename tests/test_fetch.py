"""Test della raccolta e del troncamento (Fase 2).

Basati sui criteri di accettazione del Tester, Notion sezione 16:
- 16.1 Ingestion & fonti (fail-soft, fetch_ok vs fetch_failed)
- 16.2 Troncamento estratti (500 su confine di parola; no-limit per alcune fonti)
Include lo scenario Given/When/Then "Fetch fallito, non confuso con nessun
articolo nuovo" (parte fetch; il conteggio 3 run consecutivi e' in Fase 5).

Il parser dei feed e' iniettato (`parse=`): nessuna dipendenza dalla rete.
"""
from pathlib import Path

from src.tools.fetch import (
    STATO_FETCH_FAILED,
    STATO_OK,
    fetch_candidates,
    fetch_fonte,
    fetch_tutte,
    tronca_su_parola,
)

FEED = Path(__file__).resolve().parent.parent / "sample-output" / "sample-feed.xml"


# --- parser finti ------------------------------------------------------------

class FakeFeed:
    def __init__(self, entries, bozo=0, bozo_exception=None):
        self.entries = entries
        self.bozo = bozo
        self.bozo_exception = bozo_exception
        self.feed = {}


def parser_da_mappa(mappa):
    """Ritorna un parser che, per ogni url, restituisce un FakeFeed o solleva."""
    def parse(url):
        val = mappa[url]
        if isinstance(val, Exception):
            raise val
        return val
    return parse


def _entry(titolo="T", link="https://x/1", summary="riassunto", published="2026-07-09"):
    return {"title": titolo, "link": link, "summary": summary, "published": published}


# --- 16.2 Troncamento --------------------------------------------------------

def test_troncamento_none_non_taglia():
    testo = "parola " * 200  # ~1400 caratteri
    assert tronca_su_parola(testo, None) == testo


def test_troncamento_sotto_limite_invariato():
    assert tronca_su_parola("breve", 500) == "breve"


def test_troncamento_500_su_confine_di_parola():
    cleaned = ("alpha bravo charlie delta echo foxtrot golf hotel india " * 20).strip()
    assert len(cleaned) > 500
    out = tronca_su_parola(cleaned, 500)
    assert len(out) <= 500
    # nessun taglio a meta' parola: il carattere successivo nel testo originale
    # (in corrispondenza della fine del troncato) e' uno spazio (confine).
    assert cleaned[len(out)] == " "
    assert not out.endswith(" ")


def test_troncamento_applicato_in_fetch_per_fonte_con_limite():
    lungo = "dato " * 300
    feed = FakeFeed([_entry(summary=lungo)])
    fonte = {"nome": "Con limite", "url": "u", "tema": "chip", "troncamento": 500}
    esito = fetch_fonte(fonte, parse=parser_da_mappa({"u": feed}))
    assert esito.stato == STATO_OK
    assert len(esito.candidati[0].estratto) <= 500


def test_nessun_troncamento_per_fonti_no_limit():
    lungo = "abstract accademico denso " * 100
    feed = FakeFeed([_entry(summary=lungo)])
    fonte = {"nome": "arXiv", "url": "u", "tema": "energia", "troncamento": None, "max": None}
    esito = fetch_fonte(fonte, parse=parser_da_mappa({"u": feed}))
    # l'estratto conserva l'intera lunghezza (a meno della normalizzazione spazi)
    assert len(esito.candidati[0].estratto) > 500


# --- 16.1 Stati per fonte: ok vs fetch_failed --------------------------------

def test_fetch_ok_con_voci():
    feed = FakeFeed([_entry(), _entry(link="https://x/2")])
    esito = fetch_fonte({"nome": "F", "url": "u", "tema": "chip"}, parse=parser_da_mappa({"u": feed}))
    assert esito.stato == STATO_OK
    assert esito.ok and not esito.zero_voci
    assert len(esito.candidati) == 2


def test_fetch_ok_zero_voci_distinto_da_failed():
    # feed valido ma vuoto: e' un successo con zero voci, NON un fallimento.
    feed = FakeFeed([])
    esito = fetch_fonte({"nome": "F", "url": "u", "tema": "chip"}, parse=parser_da_mappa({"u": feed}))
    assert esito.stato == STATO_OK
    assert esito.zero_voci is True


def test_fetch_failed_su_errore_http():
    # Scenario 16: fonte che solleva errore -> stato fetch_failed, mai "ok/zero".
    mappa = {"u": RuntimeError("HTTP 503 Service Unavailable")}
    esito = fetch_fonte({"nome": "KO", "url": "u", "tema": "chip"}, parse=parser_da_mappa(mappa))
    assert esito.stato == STATO_FETCH_FAILED
    assert esito.zero_voci is False   # NON confuso con "nessun articolo nuovo"
    assert esito.errore


def test_fetch_failed_su_feed_malformato():
    # bozo=1 senza entries -> feed irrecuperabile -> fetch_failed.
    feed = FakeFeed([], bozo=1, bozo_exception="mismatched tag")
    esito = fetch_fonte({"nome": "malformato", "url": "u", "tema": "chip"}, parse=parser_da_mappa({"u": feed}))
    assert esito.stato == STATO_FETCH_FAILED


def test_fail_soft_una_fonte_ko_non_blocca_le_altre():
    mappa = {
        "ok1": FakeFeed([_entry(link="https://a/1")]),
        "ko": ConnectionError("timeout"),
        "ok2": FakeFeed([_entry(link="https://b/1"), _entry(link="https://b/2")]),
    }
    cfg = {"fonti": [
        {"nome": "A", "url": "ok1", "tema": "chip"},
        {"nome": "KO", "url": "ko", "tema": "data_center"},
        {"nome": "B", "url": "ok2", "tema": "cloud_capacity"},
    ]}
    esiti = fetch_tutte(cfg, parse=parser_da_mappa(mappa))
    stati = {e.nome: e.stato for e in esiti}
    assert stati == {"A": STATO_OK, "KO": STATO_FETCH_FAILED, "B": STATO_OK}
    # i candidati delle fonti OK restano disponibili nonostante il fallimento in mezzo
    assert len(fetch_candidates(cfg, parse=parser_da_mappa(mappa))) == 3


def test_max_limita_il_numero_di_voci_lette():
    feed = FakeFeed([_entry(link=f"https://x/{i}") for i in range(10)])
    fonte = {"nome": "F", "url": "u", "tema": "chip", "max": 3}
    esito = fetch_fonte(fonte, parse=parser_da_mappa({"u": feed}))
    assert len(esito.candidati) == 3


# --- regressione: parsing reale del feed di esempio locale -------------------

def test_fetch_da_feed_locale_reale():
    cfg = {"fonti": [{"nome": "Esempio", "url": str(FEED), "tema": "chip", "max": 10}]}
    cands = fetch_candidates(cfg)
    assert len(cands) == 4
    assert all(c.url.startswith("http") for c in cands)
    assert all(c.tema == "chip" for c in cands)
