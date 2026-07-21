"""Test della deduplicazione (Fase 4).

Basati sui criteri di accettazione del Tester, Notion sez. 16.4, inclusi i 4
scenari Given/When/Then:
- Duplicato reale, nessun segnale di novita' -> scartato
- Aggiornamento legittimo per nuovo dato numerico -> incluso
- Aggiornamento legittimo per nuova entita' -> incluso
- Overlap basso -> distinto, nessun controllo di segnali
Piu' hash esatto, finestra temporale 4-6 settimane e dedup nello stesso run.
"""
from datetime import datetime, timedelta, timezone

from src.state import SeenStore
from src.raccolta.dedup import (
    cifre_salienti,
    collassa_storie,
    deduplica,
    estrai_numeri,
    hash_esatto,
    jaccard,
    normalizza_titolo,
    parole_significative,
    registra_pubblicati,
    valuta_coppia,
)
from src.raccolta.fetch import Candidato

ORA = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _cand(titolo, estratto="", url="https://x/1"):
    return Candidato(titolo=titolo, url=url, fonte="F", tema="chip",
                     data="2026-07-09", estratto=estratto)


# --- funzioni di base -------------------------------------------------------

def test_hash_esatto_stabile_e_normalizzato():
    h1 = hash_esatto("NVIDIA: Nuovo chip!", "https://a.com/x/")
    h2 = hash_esatto("nvidia nuovo chip", "https://a.com/x")
    assert h1 == h2  # titolo normalizzato + url senza slash finale


def test_normalizza_titolo():
    assert normalizza_titolo("  Città-Stato: TSMC & ASML!  ") == "citta stato tsmc asml"


def test_jaccard_estremi():
    assert jaccard(set(), set()) == 0.0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a", "b"}, {"a", "c"}) == 1 / 3


def test_estrai_numeri_ignora_numeri_nudi_ma_prende_unita():
    numeri = estrai_numeri("investimento da 2 miliardi nel 2026, banda 3,2 Tbps, 5nm")
    assert any("mld" in n for n in numeri)      # 2 miliardi
    assert any("tbps" in n for n in numeri)     # 3,2 Tbps
    assert any("nm" in n for n in numeri)       # 5nm
    assert "2026" not in numeri                 # anno nudo ignorato


# --- Scenario: duplicato reale, nessun segnale di novita' -------------------

def test_scenario_duplicato_nessun_segnale():
    a = "NVIDIA annuncia un investimento in un data center da 2 miliardi di dollari in Arizona"
    b = "NVIDIA annuncia un nuovo investimento in un data center da 2 miliardi di dollari in Arizona"
    esito = valuta_coppia(b, a, soglia=0.7)
    assert esito.overlap >= 0.7
    assert esito.segnali == []
    assert esito.decisione == "duplicato"


# --- Scenario: aggiornamento legittimo, nuovo dato numerico -----------------

def test_scenario_aggiornamento_numerico():
    a = "Meta annuncia investimento in un data center da 2 miliardi di dollari"
    b = "Meta annuncia investimento in un data center da 3,5 miliardi di dollari"
    esito = valuta_coppia(b, a, soglia=0.7)
    assert esito.overlap >= 0.7
    assert "numerico" in esito.segnali
    assert esito.decisione == "aggiornamento"


# --- Scenario: aggiornamento legittimo, nuova entita' -----------------------

def test_scenario_aggiornamento_nuova_entita():
    a = "Nuove restrizioni USA all export di chip avanzati verso la Cina"
    b = "Nuove restrizioni USA all export di chip avanzati verso la Cina e il Giappone"
    esito = valuta_coppia(b, a, soglia=0.7)
    assert esito.overlap >= 0.7
    assert "entita" in esito.segnali
    assert esito.decisione == "aggiornamento"


# --- Scenario: overlap basso, nessun controllo di segnali -------------------

def test_scenario_overlap_basso_distinto():
    a = "Meta annuncia investimento in un data center da 2 miliardi di dollari"
    c = "Risultati preliminari su ottimizzazione del consumo energetico dei modelli linguistici"
    esito = valuta_coppia(c, a, soglia=0.7)
    assert esito.overlap < 0.7
    assert esito.decisione == "distinto"
    assert esito.segnali == []


# --- integrazione con lo storico -------------------------------------------

def _store_con(a_testo, a_titolo="Articolo A", url="https://arch/a", ts=None):
    store = SeenStore(":memory:")
    ts = ts or ORA.isoformat()
    store.registra_articolo(hash_esatto(a_titolo, url), url,
                            normalizza_titolo(a_titolo), a_testo, ts)
    return store


def test_hash_esatto_su_storico_scartato():
    store = SeenStore(":memory:")
    c = _cand("Titolo unico", "corpo", url="https://x/1")
    registra_pubblicati([c], store)          # ora e' in archivio
    tenuti, esiti = deduplica([c], store, ora=ORA)
    assert tenuti == []
    assert esiti[0].decisione == "duplicato_esatto"


def test_dedup_esatto_nello_stesso_run():
    store = SeenStore(":memory:")
    c1 = _cand("Stesso titolo", url="https://x/1")
    c2 = _cand("Stesso titolo", url="https://x/1")  # identico -> stesso hash
    tenuti, _ = deduplica([c1, c2], store, ora=ORA)
    assert len(tenuti) == 1


def test_fuzzy_duplicato_scartato_tra_run():
    a = "NVIDIA annuncia investimento in un data center da 2 miliardi di dollari in Arizona"
    store = _store_con(a)
    b = _cand("NVIDIA data center Arizona",
              "NVIDIA annuncia un nuovo investimento in un data center da 2 miliardi di dollari in Arizona",
              url="https://x/new")
    tenuti, esiti = deduplica([b], store, ora=ORA)
    assert tenuti == []
    assert esiti[0].decisione == "duplicato"


def test_fuzzy_aggiornamento_incluso_tra_run():
    a = "Meta annuncia investimento in un data center da 2 miliardi di dollari"
    store = _store_con(a)
    b = _cand("Meta data center",
              "Meta annuncia investimento in un data center da 3,5 miliardi di dollari",
              url="https://x/new")
    tenuti, esiti = deduplica([b], store, ora=ORA)
    assert len(tenuti) == 1
    assert esiti[0].decisione == "aggiornamento"
    assert "numerico" in esiti[0].segnali


def test_finestra_temporale_esclude_articoli_vecchi():
    # A archiviato 8 settimane fa: fuori dalla finestra di 6 -> B non e' duplicato.
    a = "NVIDIA annuncia investimento in un data center da 2 miliardi di dollari in Arizona"
    vecchio_ts = (ORA - timedelta(weeks=8)).isoformat()
    store = _store_con(a, ts=vecchio_ts)
    b = _cand("NVIDIA data center Arizona",
              "NVIDIA annuncia un nuovo investimento in un data center da 2 miliardi di dollari in Arizona",
              url="https://x/new")
    tenuti, esiti = deduplica([b], store, finestra_settimane=6, ora=ORA)
    assert len(tenuti) == 1
    assert esiti[0].decisione == "nuovo"


def test_overlap_basso_incluso_come_nuovo():
    a = "Meta annuncia investimento in un data center da 2 miliardi di dollari"
    store = _store_con(a)
    c = _cand("arXiv energia",
              "Risultati preliminari su ottimizzazione del consumo energetico dei modelli",
              url="https://x/new")
    tenuti, esiti = deduplica([c], store, ora=ORA)
    assert len(tenuti) == 1
    assert esiti[0].decisione == "nuovo"


# --- compatibilita': filtra_nuove (dedup esatto per URL) --------------------

def test_filtra_nuove_persistente(tmp_path):
    from src.raccolta.dedup import filtra_nuove
    store = SeenStore(str(tmp_path / "seen.sqlite3"))
    cands = [_cand("t", url="https://a.com/1"), _cand("t", url="https://a.com/2"),
             _cand("t", url="https://a.com/1")]
    nuove = filtra_nuove(cands, store)
    assert len(nuove) == 2
    for c in nuove:
        store.mark_seen(c.url)
    assert filtra_nuove(cands, store) == []


# --- raggruppamento per storia sui feed aggregati (sez. 24) -----------------

def _cand_agg(titolo, data="2026-07-16", url=None, fonte="Google News"):
    return Candidato(titolo=titolo, url=url or f"https://x/{abs(hash(titolo))}",
                     fonte=fonte, tema="supply_chain", data=data, estratto="")


AGG = {"Google News"}


def test_collassa_le_varianti_della_stessa_notizia():
    # Caso reale del 2026-07-21: 7 testate sull'investimento TSMC da $100 mld.
    # Le riscritture non condividono le parole ma condividono azienda + cifra.
    voci = [
        _cand_agg("TSMC Adds $100 Billion to Its U.S. Spending Plan - The New York Times"),
        _cand_agg("Chipmaker TSMC to invest another $100bn in US production - Financial Times"),
        _cand_agg("Taiwan chipmaker TSMC to invest another US$100 bn in Arizona fabs - Yahoo"),
    ]
    tenuti, varianti = collassa_storie(voci, AGG)
    assert len(tenuti) == 1
    assert varianti[tenuti[0].url] == 3
    assert tenuti[0].n_testate == 3


def test_senza_cifra_non_si_accorpa_nulla():
    # Senza numero la chiave accomunerebbe notizie diverse sulla stessa azienda:
    # provato in laboratorio, collassava 10 storie ASML distinte in una.
    voci = [
        _cand_agg("ASML has room to raise prices, CFO says"),
        _cand_agg("ASML financial guidance includes Terafab plans, CFO says"),
        _cand_agg("Intel turns to next-generation ASML tool for its laptop chips"),
    ]
    tenuti, varianti = collassa_storie(voci, AGG)
    assert len(tenuti) == 3
    assert varianti == {}


def test_la_stessa_cifra_a_distanza_di_settimane_resta_distinta():
    # "100" puo' tornare per un fatto diverso: la tolleranza e' di pochi giorni.
    voci = [
        _cand_agg("TSMC to invest $100 billion in the US", data="2026-07-16"),
        _cand_agg("TSMC announces a new $100 billion plan", data="2026-09-30"),
    ]
    assert len(collassa_storie(voci, AGG)[0]) == 2


def test_la_copertura_a_cavallo_di_un_giorno_resta_unita():
    # Le testate coprono la stessa notizia su piu' giorni: pretendere la data
    # identica spezzava la coppia sul bonus ASML (19 e 20 luglio).
    voci = [
        _cand_agg("ASML to offer employees EUR 20,000 retention bonus", data="2026-07-19"),
        _cand_agg("ASML just gave workers a EUR 20,000 bonus and new shares", data="2026-07-20"),
    ]
    assert len(collassa_storie(voci, AGG)[0]) == 1


def test_le_fonti_non_aggregate_non_vengono_toccate():
    # Il raggruppamento e' opt-in: su una fonte diretta due articoli con la
    # stessa azienda e la stessa cifra sono notizie distinte, non varianti.
    voci = [
        _cand_agg("NVIDIA annuncia 100 nuovi data center", fonte="NVIDIA Blog"),
        _cand_agg("NVIDIA amplia a 100 le regioni cloud", fonte="NVIDIA Blog"),
    ]
    assert len(collassa_storie(voci, AGG)[0]) == 2


def test_anni_e_numeri_banali_non_fanno_chiave():
    # "2026" e le cifre singole compaiono ovunque: userebbero notizie senza
    # rapporto come se fossero la stessa.
    assert cifre_salienti("tsmc guidance for 2026 in q2") == set()
    assert "100" in cifre_salienti("tsmc invests $100 billion")
