"""Test dello schema dati (Fase 1).

Basati sui criteri di accettazione del Tester, Notion sezione 16:
- 16.6 Stati vuoti
- 16.7 Schema dati
Riferimento struttura: sezione 15.
"""
import pytest
from pydantic import ValidationError

from src.schemas import (
    MESSAGGIO_NESSUN_AGGIORNAMENTO,
    TEMI_ORDINE,
    Articolo,
    Digest,
    Fonte,
    NotaInterna,
    Sezione,
    Stato,
    Tema,
    TipoNotaInterna,
    digest_vuoto,
    sezione_vuota,
)


# --- helper -----------------------------------------------------------------

def _articolo(**kw) -> Articolo:
    base = dict(
        titolo="Titolo",
        fonti=[Fonte(nome="NVIDIA Newsroom", link="https://nvidia.com/x")],
        data="2026-07-09",
        sintesi="Sintesi breve.",
        perche_conta="Conta perche' impatta la capacita' di calcolo.",
    )
    base.update(kw)
    return Articolo(**base)


def _cinque_sezioni_vuote() -> list[Sezione]:
    return [sezione_vuota(t) for t in TEMI_ORDINE]


# --- 16.7 Schema dati: esattamente 5 sezioni fisse --------------------------

def test_digest_vuoto_ha_esattamente_cinque_sezioni_una_per_tema():
    d = digest_vuoto("2026-07-09")
    assert len(d.sezioni) == 5
    assert [s.tema for s in d.sezioni] == TEMI_ORDINE
    # tutte in stato distinguibile a livello di schema (16.6)
    assert all(s.stato is Stato.nessun_aggiornamento for s in d.sezioni)


def test_digest_con_quattro_sezioni_e_rifiutato():
    with pytest.raises(ValidationError):
        Digest(data_generazione="2026-07-09", sezioni=_cinque_sezioni_vuote()[:4])


def test_digest_con_tema_duplicato_e_rifiutato():
    sez = _cinque_sezioni_vuote()
    sez[1] = sezione_vuota(Tema.chip)  # due volte "chip"
    with pytest.raises(ValidationError):
        Digest(data_generazione="2026-07-09", sezioni=sez)


def test_digest_con_sezione_extra_e_rifiutato():
    sez = _cinque_sezioni_vuote() + [sezione_vuota(Tema.chip)]
    with pytest.raises(ValidationError):
        Digest(data_generazione="2026-07-09", sezioni=sez)


def test_tema_e_enum_vincolato_non_testo_libero():
    with pytest.raises(ValidationError):
        Sezione(tema="chips", stato=Stato.nessun_aggiornamento, articoli=[])


# --- 16.7 Articolo: perche_conta obbligatorio -------------------------------

def test_perche_conta_vuoto_e_rifiutato():
    with pytest.raises(ValidationError):
        _articolo(perche_conta="")


def test_perche_conta_solo_spazi_e_rifiutato():
    with pytest.raises(ValidationError):
        _articolo(perche_conta="   ")


def test_articolo_valido_con_perche_conta():
    a = _articolo()
    assert a.perche_conta


# --- 16.7 fonti e' una lista (supporta multi-testata Google News) -----------

def test_articolo_supporta_piu_fonti():
    a = _articolo(
        fonti=[
            Fonte(nome="Reuters", link="https://reuters.com/a"),
            Fonte(nome="Bloomberg", link="https://bloomberg.com/a"),
        ],
        note="ripreso da piu' testate",
    )
    assert len(a.fonti) == 2
    assert a.fonti[1].nome == "Bloomberg"


def test_fonte_con_link_vuoto_e_rifiutata():
    with pytest.raises(ValidationError):
        Fonte(nome="X", link="")


# --- 16.6 Stati vuoti: coerenza stato/articoli ------------------------------

def test_sezione_nessun_aggiornamento_non_puo_avere_articoli():
    with pytest.raises(ValidationError):
        Sezione(tema=Tema.chip, stato=Stato.nessun_aggiornamento, articoli=[_articolo()])


def test_sezione_con_aggiornamenti_richiede_almeno_un_articolo():
    with pytest.raises(ValidationError):
        Sezione(tema=Tema.chip, stato=Stato.con_aggiornamenti, articoli=[])


def test_sezione_con_aggiornamenti_valida():
    s = Sezione(tema=Tema.chip, stato=Stato.con_aggiornamenti, articoli=[_articolo()])
    assert s.stato is Stato.con_aggiornamenti
    assert len(s.articoli) == 1


def test_messaggio_stato_vuoto_e_costante_di_codice():
    # 16.6: messaggio template fisso da codice, mai generato dal modello.
    assert isinstance(MESSAGGIO_NESSUN_AGGIORNAMENTO, str)
    assert MESSAGGIO_NESSUN_AGGIORNAMENTO.strip()


# --- 16.7 note_interne: solo a livello Digest, mai nel pubblico --------------

def test_note_interne_e_a_livello_digest():
    d = digest_vuoto("2026-07-09")
    d.note_interne.append(
        NotaInterna(tipo=TipoNotaInterna.fetch_failed_ripetuto, dettaglio="Azure Blog KO x3")
    )
    assert d.note_interne[0].tipo is TipoNotaInterna.fetch_failed_ripetuto


def test_contenuto_pubblico_esclude_note_interne():
    d = digest_vuoto("2026-07-09")
    d.note_interne.append(
        NotaInterna(tipo=TipoNotaInterna.sezione_a_zero_ripetuta, dettaglio="energia 0 x3")
    )
    pubblico = d.contenuto_pubblico()
    assert "note_interne" not in pubblico
    assert "sezioni" in pubblico
    # l'oggetto originale conserva comunque le note (servono agli script)
    assert d.note_interne


def test_stato_distinguibile_nel_dump():
    # 16.6: lo stato e' un campo di schema, leggibile senza interpretare testo.
    d = digest_vuoto("2026-07-09")
    dump = d.model_dump(mode="json")
    assert dump["sezioni"][0]["stato"] == "nessun_aggiornamento"
