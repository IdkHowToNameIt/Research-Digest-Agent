"""Test delle note interne (Fase 5).

Basati sui criteri di accettazione del Tester, Notion sez. 16.1 (fetch_failed
ripetuto) e 16.3 (sezione energia a zero ripetuta), inclusi gli scenari
Given/When/Then "Fetch fallito ... 3 run consecutivi" e "Sezione energia a zero
per piu' settimane consecutive".
"""
from src.note_interne import aggiorna_e_genera_note
from src.schemas import Tema, TipoNotaInterna
from src.state import SeenStore
from src.tools.fetch import STATO_FETCH_FAILED, STATO_OK, EsitoFonte

# conteggio con almeno un articolo energia (nessuna nota energia)
_ENERGIA_OK = {Tema.energia: 2}
_ENERGIA_ZERO = {Tema.energia: 0}


def _fonte(nome, stato):
    return EsitoFonte(nome=nome, stato=stato)


def _run(store, esiti, per_tema=_ENERGIA_OK):
    return aggiorna_e_genera_note(store, esiti, per_tema)


# --- 16.1 fetch_failed ripetuto ---------------------------------------------

def test_nota_fetch_failed_dopo_tre_run_consecutivi():
    store = SeenStore(":memory:")
    ko = [_fonte("Azure Blog", STATO_FETCH_FAILED)]
    assert _run(store, ko) == []          # run 1
    assert _run(store, ko) == []          # run 2
    note = _run(store, ko)                # run 3 -> nota
    assert len(note) == 1
    assert note[0].tipo is TipoNotaInterna.fetch_failed_ripetuto
    assert "Azure Blog" in note[0].dettaglio


def test_fetch_ok_zero_voci_non_conta_come_fallimento():
    # Scenario 16: un fetch riuscito ma vuoto NON e' un fallimento -> nessuna nota.
    store = SeenStore(":memory:")
    ok_vuoto = [_fonte("NVIDIA Blog", STATO_OK)]
    for _ in range(5):
        assert _run(store, ok_vuoto) == []


def test_contatore_fetch_si_azzera_su_successo():
    store = SeenStore(":memory:")
    nome = "Meta Engineering"
    _run(store, [_fonte(nome, STATO_FETCH_FAILED)])   # 1
    _run(store, [_fonte(nome, STATO_FETCH_FAILED)])   # 2
    _run(store, [_fonte(nome, STATO_OK)])             # reset
    note = _run(store, [_fonte(nome, STATO_FETCH_FAILED)])  # 1 di nuovo
    assert note == []


def test_contatori_fonti_indipendenti():
    store = SeenStore(":memory:")
    esiti = [_fonte("A", STATO_FETCH_FAILED), _fonte("B", STATO_OK)]
    _run(store, esiti)
    _run(store, esiti)
    note = _run(store, esiti)  # solo A raggiunge 3
    assert len(note) == 1
    assert "A" in note[0].dettaglio


# --- 16.3 sezione energia a zero ripetuta -----------------------------------

def test_nota_energia_dopo_tre_run_a_zero():
    store = SeenStore(":memory:")
    ok_fonti = [_fonte("arXiv", STATO_OK)]
    assert _run(store, ok_fonti, _ENERGIA_ZERO) == []      # run 1
    assert _run(store, ok_fonti, _ENERGIA_ZERO) == []      # run 2
    note = _run(store, ok_fonti, _ENERGIA_ZERO)            # run 3 -> nota
    assert len(note) == 1
    assert note[0].tipo is TipoNotaInterna.sezione_a_zero_ripetuta


def test_energia_con_articoli_azzera_il_contatore():
    store = SeenStore(":memory:")
    ok_fonti = [_fonte("arXiv", STATO_OK)]
    _run(store, ok_fonti, _ENERGIA_ZERO)  # 1
    _run(store, ok_fonti, _ENERGIA_ZERO)  # 2
    _run(store, ok_fonti, _ENERGIA_OK)    # reset
    note = _run(store, ok_fonti, _ENERGIA_ZERO)  # 1 di nuovo
    assert note == []


def test_nota_e_solo_segnalazione_non_blocco():
    # la funzione restituisce solo note (nessun effetto collaterale di blocco):
    # non modifica ne' i conteggi per tema ne' altro se non i contatori interni.
    store = SeenStore(":memory:")
    per_tema = {Tema.energia: 0}
    for _ in range(3):
        note = aggiorna_e_genera_note(store, [], per_tema)
    assert note and note[0].tipo is TipoNotaInterna.sezione_a_zero_ripetuta
    # il dizionario di input non viene alterato
    assert per_tema == {Tema.energia: 0}
