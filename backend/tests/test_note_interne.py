"""Test delle note interne (Fase 5).

Basati sui criteri di accettazione del Tester, Notion sez. 16.1 (fetch_failed
ripetuto) e 16.3 (sezione energia a zero ripetuta). Dal 2026-07-23 la soglia di
default e' 1 (scelta dell'utente): la nota parte al PRIMO run con la fonte in
errore o la sezione a zero. La soglia resta un parametro: i test multi-run la
passano esplicita.
"""
from src.consegna.note_interne import aggiorna_e_genera_note, SOGLIA_RUN_CONSECUTIVI
from src.schemas import Tema, TipoNotaInterna
from src.state import SeenStore
from src.raccolta.fetch import STATO_FETCH_FAILED, STATO_OK, EsitoFonte

# conteggio con almeno un articolo energia (nessuna nota energia)
_ENERGIA_OK = {Tema.energia: 2}
_ENERGIA_ZERO = {Tema.energia: 0}


def _fonte(nome, stato):
    return EsitoFonte(nome=nome, stato=stato)


def _run(store, esiti, per_tema=_ENERGIA_OK, **kw):
    return aggiorna_e_genera_note(store, esiti, per_tema, **kw)


# --- 16.1 fetch_failed -------------------------------------------------------

def test_soglia_default_e_uno():
    # la scelta del 2026-07-23: notifica immediata, non dopo tre settimane
    assert SOGLIA_RUN_CONSECUTIVI == 1


def test_nota_fetch_failed_al_primo_run():
    store = SeenStore(":memory:")
    note = _run(store, [_fonte("Azure Blog", STATO_FETCH_FAILED)])
    assert len(note) == 1
    assert note[0].tipo is TipoNotaInterna.fetch_failed_ripetuto
    assert "Azure Blog" in note[0].dettaglio


def test_soglia_parametrica_tre_run():
    # la soglia resta un parametro: con 3 il comportamento storico e' invariato
    store = SeenStore(":memory:")
    ko = [_fonte("Azure Blog", STATO_FETCH_FAILED)]
    assert _run(store, ko, soglia=3) == []          # run 1
    assert _run(store, ko, soglia=3) == []          # run 2
    note = _run(store, ko, soglia=3)                # run 3 -> nota
    assert len(note) == 1


def test_fetch_ok_zero_voci_non_conta_come_fallimento():
    # Scenario 16: un fetch riuscito ma vuoto NON e' un fallimento -> nessuna nota.
    store = SeenStore(":memory:")
    ok_vuoto = [_fonte("NVIDIA Blog", STATO_OK)]
    for _ in range(5):
        assert _run(store, ok_vuoto) == []


def test_contatore_fetch_si_azzera_su_successo():
    # con soglia 2: un fallimento, un successo (reset), un fallimento -> il
    # contatore e' ripartito da 1 e non scatta nulla
    store = SeenStore(":memory:")
    nome = "Meta Engineering"
    assert _run(store, [_fonte(nome, STATO_FETCH_FAILED)], soglia=2) == []
    _run(store, [_fonte(nome, STATO_OK)], soglia=2)             # reset
    note = _run(store, [_fonte(nome, STATO_FETCH_FAILED)], soglia=2)
    assert note == []


def test_contatori_fonti_indipendenti():
    store = SeenStore(":memory:")
    esiti = [_fonte("A", STATO_FETCH_FAILED), _fonte("B", STATO_OK)]
    note = _run(store, esiti)  # solo A fallisce -> una sola nota
    assert len(note) == 1
    assert "A" in note[0].dettaglio


# --- 16.3 sezione energia a zero ---------------------------------------------

def test_nota_energia_al_primo_run_a_zero():
    store = SeenStore(":memory:")
    ok_fonti = [_fonte("arXiv", STATO_OK)]
    note = _run(store, ok_fonti, _ENERGIA_ZERO)
    assert len(note) == 1
    assert note[0].tipo is TipoNotaInterna.sezione_a_zero_ripetuta


def test_energia_con_articoli_azzera_il_contatore():
    # con soglia 2: zero (1), articoli (reset), zero (1) -> nessuna nota
    store = SeenStore(":memory:")
    ok_fonti = [_fonte("arXiv", STATO_OK)]
    assert _run(store, ok_fonti, _ENERGIA_ZERO, soglia=2) == []
    _run(store, ok_fonti, _ENERGIA_OK, soglia=2)      # reset
    note = _run(store, ok_fonti, _ENERGIA_ZERO, soglia=2)
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
