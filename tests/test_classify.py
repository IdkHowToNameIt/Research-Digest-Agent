"""Test della classificazione sotto-temi e del filtro di rilevanza (Fase 3).

Basati sui criteri di accettazione del Tester, Notion sez. 16.3 (classificazione)
e sez. 13/16.2 (filtro di rilevanza tematica a monte per Google Cloud Blog).
"""
from src.classify import classifica, is_rilevante, raggruppa_per_tema
from src.schemas import Tema
from src.tools.fetch import Candidato


def _cand(titolo="T", estratto="", tema="chip", filtro=False, url="https://x/1"):
    return Candidato(
        titolo=titolo, url=url, fonte="F", tema=tema, data="2026-07-09",
        estratto=estratto, filtro_rilevanza=filtro,
    )


# --- 16.3 Ogni articolo -> esattamente un tema o None -----------------------

def test_classifica_ritorna_tema_della_fonte():
    assert classifica(_cand(tema="supply_chain")) is Tema.supply_chain


def test_classifica_sempre_tema_singolo_o_none():
    for c in [_cand(tema="chip"), _cand(tema="energia"), _cand(tema="cloud_capacity")]:
        risultato = classifica(c)
        assert risultato is None or isinstance(risultato, Tema)


def test_tema_non_valido_va_a_revisione_manuale():
    assert classifica(_cand(tema="semiconduttori")) is None


# --- 16.2 Filtro di rilevanza a monte (Google Cloud Blog) -------------------

def test_fonte_senza_filtro_sempre_rilevante():
    # una fonte gia' scoped al beat non viene filtrata, anche se il testo e' generico
    c = _cand(titolo="Aggiornamento prodotto", estratto="novita' varie", filtro=False)
    assert is_rilevante(c) is True
    assert classifica(c) is Tema.chip


def test_google_cloud_blog_in_beat_classificato():
    c = _cand(
        titolo="New GPU-to-GPU bandwidth in our data center fabric",
        estratto="3.2 Tbps interconnect for AI clusters",
        tema="cloud_capacity", filtro=True,
    )
    assert is_rilevante(c) is True
    assert classifica(c) is Tema.cloud_capacity


def test_google_cloud_blog_fuori_beat_scartato():
    # contenuto database/sicurezza senza parole del beat -> None (revisione manuale)
    c = _cand(
        titolo="New database features and threat intelligence updates",
        estratto="improved SQL analytics and security posture management",
        tema="cloud_capacity", filtro=True,
    )
    assert is_rilevante(c) is False
    assert classifica(c) is None


# --- Raggruppamento: 5 chiavi sempre presenti, conteggi coerenti ------------

def test_raggruppa_ha_sempre_cinque_temi():
    gruppi, scartati = raggruppa_per_tema([])
    assert set(gruppi.keys()) == set(Tema)
    assert all(v == [] for v in gruppi.values())
    assert scartati == []


def test_raggruppa_conteggi_e_scartati():
    candidati = [
        _cand(tema="chip", url="https://x/1"),
        _cand(tema="chip", url="https://x/2"),
        _cand(tema="data_center", url="https://x/3"),
        # off-beat da fonte con filtro -> scartato
        _cand(titolo="database security", estratto="sql", tema="cloud_capacity",
              filtro=True, url="https://x/4"),
        # tema non valido -> scartato
        _cand(tema="qualcosa", url="https://x/5"),
    ]
    gruppi, scartati = raggruppa_per_tema(candidati)
    assert len(gruppi[Tema.chip]) == 2
    assert len(gruppi[Tema.data_center]) == 1
    assert len(gruppi[Tema.energia]) == 0
    assert len(scartati) == 2
    # nessun articolo perso: somma raggruppati + scartati == input
    totale = sum(len(v) for v in gruppi.values()) + len(scartati)
    assert totale == len(candidati)


def test_nessun_articolo_in_piu_di_un_tema():
    candidati = [_cand(tema="energia", url=f"https://x/{i}") for i in range(3)]
    gruppi, _ = raggruppa_per_tema(candidati)
    tutti_url = [c.url for v in gruppi.values() for c in v]
    assert len(tutti_url) == len(set(tutti_url))  # nessun duplicato tra i temi
