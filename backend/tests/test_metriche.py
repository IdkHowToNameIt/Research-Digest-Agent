"""Metriche operative per run (src/metriche.py): raccolta durante la pipeline,
stima di costo dal listino, e I/O (un JSON per run, gemello dell'archivio).

Tutto offline: feed via parser iniettato, modello in modalità demo (genera=None),
store in memoria. L'uso di token del modello reale arriva via callback in
produzione; qui si verifica la contabilizzazione con `registra_uso` diretto.
"""
from datetime import datetime, timezone

import json

from src.metriche import (
    RaccoltaMetriche,
    _stima_costo,
    carica_metriche,
    costruisci_dati_dashboard,
    salva_metriche,
    scrivi_dashboard,
)
from src.pipeline import costruisci_digest
from src.state import SeenStore

ORA = datetime(2026, 7, 9, tzinfo=timezone.utc)


# --- helper: pipeline offline (come test_pipeline) --------------------------
class FakeFeed:
    def __init__(self, entries):
        self.entries = entries
        self.bozo = 0
        self.feed = {}


def _entry(titolo, link, summary="corpo dell'articolo con contenuto"):
    return {"title": titolo, "link": link, "summary": summary, "published": "2026-07-09"}


def _parser(mappa):
    def parse(url):
        val = mappa[url]
        if isinstance(val, Exception):
            raise val          # simula un feed irraggiungibile (fetch_failed)
        return val
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


# --- raccolta dai dati operativi del run ------------------------------------
def test_dedup_conta_raccolti_e_pubblicati():
    store = SeenStore(":memory:")
    racc = RaccoltaMetriche()
    costruisci_digest(_cfg(), genera=None, store=store, ora=ORA,
                      parse=_parser(_mappa()), metriche=racc)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    assert rec.dedup.raccolti == 3
    assert rec.dedup.nuovi == 3
    assert rec.dedup.pubblicati == 3
    assert rec.dedup.duplicati_esatti == 0


def test_dedup_duplicati_esatti_al_secondo_run():
    store = SeenStore(":memory:")
    cfg = _cfg()
    # primo run: popola lo storico
    costruisci_digest(cfg, genera=None, store=store, ora=ORA, parse=_parser(_mappa()))
    # secondo run identico: tutto già visto
    racc = RaccoltaMetriche()
    costruisci_digest(cfg, genera=None, store=store, ora=ORA,
                      parse=_parser(_mappa()), metriche=racc)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    assert rec.dedup.duplicati_esatti == 3
    assert rec.dedup.pubblicati == 0


def test_copertura_stato_e_conteggi_per_tema():
    store = SeenStore(":memory:")
    racc = RaccoltaMetriche()
    costruisci_digest(_cfg(), genera=None, store=store, ora=ORA,
                      parse=_parser(_mappa()), metriche=racc)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    cop = {c.tema: c for c in rec.copertura}
    assert len(rec.copertura) == 5                       # sempre i 5 temi
    assert cop["chip"].stato == "con_aggiornamenti" and cop["chip"].n_articoli == 2
    assert cop["cloud_capacity"].n_articoli == 1
    assert cop["energia"].stato == "nessun_aggiornamento" and cop["energia"].n_articoli == 0


def test_energia_zero_consecutivi_incrementa():
    store = SeenStore(":memory:")
    racc = RaccoltaMetriche()
    # nessuna fonte energia -> sezione a zero -> contatore a 1 dopo un run
    costruisci_digest(_cfg(), genera=None, store=store, ora=ORA,
                      parse=_parser(_mappa()), metriche=racc)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    assert rec.energia_zero_consecutivi == 1


def test_fonti_stato_ok_e_fetch_failed():
    store = SeenStore(":memory:")
    racc = RaccoltaMetriche()
    mappa = _mappa()
    mappa["cloud"] = ValueError("feed irraggiungibile")   # una fonte KO
    costruisci_digest(_cfg(), genera=None, store=store, ora=ORA,
                      parse=_parser(mappa), metriche=racc)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    stato = {f.nome: f for f in rec.fonti}
    assert stato["NVIDIA Blog"].stato == "ok"
    assert stato["NVIDIA Blog"].n_candidati == 2
    assert stato["AWS News Blog"].stato == "fetch_failed"
    assert stato["AWS News Blog"].consecutivi_falliti == 1   # primo fallimento


# --- uso token e stima di costo ---------------------------------------------
def test_registra_uso_somma_per_modello():
    racc = RaccoltaMetriche()
    racc.registra_uso("llama-3.3-70b-versatile", 100, 50)
    racc.registra_uso("llama-3.3-70b-versatile", 200, 30)
    racc.registra_uso("gemma2-9b-it", 10, 5)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    per_modello = {m.modello: m for m in rec.costo.modelli}
    assert per_modello["llama-3.3-70b-versatile"].chiamate == 2
    assert per_modello["llama-3.3-70b-versatile"].prompt_tokens == 300
    assert per_modello["llama-3.3-70b-versatile"].completion_tokens == 80
    assert rec.costo.prompt_tokens == 310          # 300 + 10
    assert rec.costo.completion_tokens == 85       # 80 + 5


def test_stima_costo_dal_listino():
    # €1/1M input, €2/1M output
    prezzi = {"m": {"input": 1.0, "output": 2.0}}
    assert _stima_costo(prezzi, "m", 1_000_000, 500_000) == 2.0   # 1.0 + 1.0
    # modello assente dal listino -> costo 0 (free tier), token comunque contati
    assert _stima_costo(prezzi, "sconosciuto", 1_000_000, 1_000_000) == 0.0


def test_costo_totale_applica_listino():
    racc = RaccoltaMetriche()
    racc.registra_uso("m", 2_000_000, 1_000_000)
    rec = racc.finalizza({"m": {"input": 1.0, "output": 3.0}}, "2026-07-09",
                         "2026-07-09T05:40:00Z")
    assert rec.costo.costo_stimato == 5.0          # 2*1 + 1*3
    assert rec.costo.modelli[0].costo_stimato == 5.0


def test_free_tier_costo_zero_ma_token_contati():
    racc = RaccoltaMetriche()
    racc.registra_uso("m", 5000, 3000)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")   # listino vuoto
    assert rec.costo.costo_stimato == 0.0
    assert rec.costo.prompt_tokens == 5000 and rec.costo.completion_tokens == 3000


# --- I/O: un file per run, round-trip ---------------------------------------
def test_salva_e_carica_round_trip(tmp_path):
    racc = RaccoltaMetriche()
    racc.registra_uso("m", 100, 50)
    rec = racc.finalizza({}, "2026-07-09", "2026-07-09T05:40:00Z")
    percorso = salva_metriche(rec, str(tmp_path))
    # nome file sicuro su ogni OS: niente ':' del timestamp ISO
    assert ":" not in percorso.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    caricati = carica_metriche(str(tmp_path))
    assert len(caricati) == 1
    assert caricati[0].timestamp == "2026-07-09T05:40:00Z"
    assert caricati[0].costo.prompt_tokens == 100


def test_carica_ordina_per_timestamp(tmp_path):
    for ts in ("2026-07-14T05:40:00Z", "2026-07-07T05:40:00Z", "2026-07-21T05:40:00Z"):
        rec = RaccoltaMetriche().finalizza({}, ts[:10], ts)
        salva_metriche(rec, str(tmp_path))
    caricati = carica_metriche(str(tmp_path))
    assert [r.timestamp for r in caricati] == [
        "2026-07-07T05:40:00Z", "2026-07-14T05:40:00Z", "2026-07-21T05:40:00Z",
    ]


def test_carica_da_cartella_inesistente(tmp_path):
    assert carica_metriche(str(tmp_path / "non-esiste")) == []


# --- dati per la dashboard del sito -----------------------------------------
def _record(ts, prompt=0, completion=0):
    r = RaccoltaMetriche()
    if prompt or completion:
        r.registra_uso("m", prompt, completion)
    return r.finalizza({}, ts[:10], ts)


def test_dashboard_run_dal_piu_recente():
    dati = costruisci_dati_dashboard([
        _record("2026-07-07T05:40:00Z"),
        _record("2026-07-21T05:40:00Z"),
        _record("2026-07-14T05:40:00Z"),
    ])
    assert dati["generato"] == "2026-07-21T05:40:00Z"       # ultimo run
    assert [r["timestamp"] for r in dati["run"]] == [
        "2026-07-21T05:40:00Z", "2026-07-14T05:40:00Z", "2026-07-07T05:40:00Z",
    ]
    assert dati["temi"] == ["chip", "data_center", "energia", "supply_chain", "cloud_capacity"]


def test_dashboard_vuota_senza_run():
    dati = costruisci_dati_dashboard([])
    assert dati["generato"] == "" and dati["run"] == []


def test_dashboard_run_e_serializzabile_e_completo():
    dati = costruisci_dati_dashboard([_record("2026-07-14T05:40:00Z", 100, 50)])
    run = dati["run"][0]
    # il record esposto al frontend contiene tutte le sezioni della dashboard
    assert set(run) >= {"fonti", "dedup", "copertura", "energia_zero_consecutivi", "costo"}
    assert run["costo"]["prompt_tokens"] == 100


def test_scrivi_dashboard_produce_json_valido(tmp_path):
    percorso = scrivi_dashboard([_record("2026-07-14T05:40:00Z", 10, 5)], str(tmp_path))
    assert percorso.endswith("metriche.json")
    dati = json.loads((tmp_path / "metriche.json").read_text(encoding="utf-8"))
    assert len(dati["run"]) == 1 and dati["generato"] == "2026-07-14T05:40:00Z"
