"""Test di integrazione della pipeline (Fase 6), tutto offline.

Feed via parser iniettato, modello in modalita' demo (genera=None), store in
memoria. Verifica il flusso fetch -> dedup -> classificazione -> assemblaggio e
la persistenza del dedup tra run consecutivi.
"""
from datetime import datetime, timezone

from src.pipeline import costruisci_digest
from src.schemas import Digest, Stato, Tema
from src.state import SeenStore

ORA = datetime(2026, 7, 9, tzinfo=timezone.utc)


class FakeFeed:
    def __init__(self, entries):
        self.entries = entries
        self.bozo = 0
        self.feed = {}


def _entry(titolo, link, summary="corpo dell'articolo con contenuto"):
    return {"title": titolo, "link": link, "summary": summary, "published": "2026-07-09"}


def _parser(mappa):
    def parse(url):
        return mappa[url]
    return parse


def _cfg():
    return {
        "db_path": ":memory:",
        "soglia_overlap_dedup": 0.7,
        "finestra_dedup_settimane": 6,
        "fonti": [
            {"nome": "NVIDIA Blog", "url": "chip", "tema": "chip"},
            {"nome": "AWS News Blog", "url": "cloud", "tema": "cloud_capacity"},
        ],
    }


def _mappa():
    return {
        "chip": FakeFeed([_entry("Nuovo chip Blackwell", "https://n/1"),
                          _entry("GPU per data center", "https://n/2")]),
        "cloud": FakeFeed([_entry("Nuova regione cloud", "https://a/1")]),
    }


def test_pipeline_demo_produce_digest_valido():
    store = SeenStore(":memory:")
    d = costruisci_digest(_cfg(), genera=None, store=store, ora=ORA, parse=_parser(_mappa()))
    assert isinstance(d, Digest)
    assert len(d.sezioni) == 5
    assert d.sezione(Tema.chip).stato is Stato.con_aggiornamenti
    assert len(d.sezione(Tema.chip).articoli) == 2
    assert d.sezione(Tema.cloud_capacity).stato is Stato.con_aggiornamenti
    # sezioni senza fonti -> nessun_aggiornamento
    assert d.sezione(Tema.energia).stato is Stato.nessun_aggiornamento
    # con soglia 1 (dal 2026-07-23) la sezione energia a zero genera la nota
    # gia' al primo run: e' l'unica attesa
    assert len(d.note_interne) == 1
    assert "energia" in d.note_interne[0].dettaglio


def test_pipeline_dedup_tra_run_consecutivi():
    store = SeenStore(":memory:")
    cfg = _cfg()
    d1 = costruisci_digest(cfg, genera=None, store=store, ora=ORA, parse=_parser(_mappa()))
    assert sum(len(s.articoli) for s in d1.sezioni) == 3
    # secondo run con gli stessi identici articoli: tutti gia' visti -> zero nuovi
    d2 = costruisci_digest(cfg, genera=None, store=store, ora=ORA, parse=_parser(_mappa()))
    assert sum(len(s.articoli) for s in d2.sezioni) == 0
    assert all(s.stato is Stato.nessun_aggiornamento for s in d2.sezioni)


def test_pipeline_grounding_link_reali():
    store = SeenStore(":memory:")
    d = costruisci_digest(_cfg(), genera=None, store=store, ora=ORA, parse=_parser(_mappa()))
    link = [f.link for s in d.sezioni for a in s.articoli for f in a.fonti]
    assert set(link) == {"https://n/1", "https://n/2", "https://a/1"}
