"""Test dell'email settimanale (Fase 7).

Basati sugli scenari Given/When/Then della sez. 17.1:
- notifica di aggiornamenti disponibili (oggetto termina in "- DRA", rimanda alla
  homepage, senza elencare tema/titolo/link);
- reminder quando tutte le sezioni sono "nessun_aggiornamento";
- esattamente un'email settimanale (mai entrambe, mai nessuna).
Piu' l'email separata di note interne (17.2).
"""
from src.consegna.notifica import (
    CORPO_REMINDER,
    DIGEST_AGGIORNAMENTI,
    DIGEST_REMINDER,
    NOTE_INTERNE,
    OGGETTO_REMINDER,
    componi_email_note_interne,
    invia_tutti,
    prepara_invii,
)
from src.schemas import (
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

HOMEPAGE = "https://intranet.example/dra"
CFG = {
    "sito": {"homepage_url": HOMEPAGE},
    "email": {
        "destinatari_digest": ["team@example.com"],
        "destinatari_note_interne": ["it@example.com"],
    },
}


def _articolo():
    return Articolo(
        titolo="Titolo segreto da non mettere in email",
        fonti=[Fonte(nome="NVIDIA", link="https://link/da/non/elencare")],
        data="2026-07-09", sintesi="s.", perche_conta="p.",
    )


def _digest_con_aggiornamenti() -> Digest:
    sezioni = [sezione_vuota(t) for t in Tema]
    sezioni[0] = Sezione(tema=Tema.chip, stato=Stato.con_aggiornamenti, articoli=[_articolo()])
    return Digest(data_generazione="2026-07-09", sezioni=sezioni)


# --- Scenario: notifica di aggiornamenti ------------------------------------

def test_notifica_quando_ci_sono_aggiornamenti():
    invii = prepara_invii(_digest_con_aggiornamenti(), CFG)
    settimanali = [m for m in invii if m.tipo in (DIGEST_AGGIORNAMENTI, DIGEST_REMINDER)]
    assert len(settimanali) == 1
    msg = settimanali[0]
    assert msg.tipo == DIGEST_AGGIORNAMENTI
    assert msg.oggetto.endswith("- DRA")
    assert HOMEPAGE in msg.corpo
    # non elenca tema/titolo/link dei singoli articoli
    assert "Titolo segreto da non mettere in email" not in msg.corpo
    assert "https://link/da/non/elencare" not in msg.corpo
    assert msg.destinatari == ["team@example.com"]


# --- Scenario: reminder, nessun aggiornamento -------------------------------

def test_reminder_quando_nessun_aggiornamento():
    invii = prepara_invii(digest_vuoto("2026-07-09"), CFG)
    settimanali = [m for m in invii if m.tipo in (DIGEST_AGGIORNAMENTI, DIGEST_REMINDER)]
    assert len(settimanali) == 1
    msg = settimanali[0]
    assert msg.tipo == DIGEST_REMINDER
    assert msg.oggetto == OGGETTO_REMINDER
    assert msg.corpo == CORPO_REMINDER
    # non elenca i singoli temi
    for tema in Tema:
        assert tema.value not in msg.corpo


# --- Scenario: esattamente un'email settimanale -----------------------------

def test_sempre_esattamente_una_email_settimanale():
    for digest in (_digest_con_aggiornamenti(), digest_vuoto("2026-07-09")):
        invii = prepara_invii(digest, CFG)
        settimanali = [m for m in invii if m.tipo in (DIGEST_AGGIORNAMENTI, DIGEST_REMINDER)]
        assert len(settimanali) == 1  # mai zero, mai due


# --- Note interne: email separata (17.2) ------------------------------------

def test_email_note_interne_solo_se_presenti():
    assert componi_email_note_interne([], ["it@example.com"]) is None
    note = [NotaInterna(tipo=TipoNotaInterna.fetch_failed_ripetuto, dettaglio="Azure KO x3")]
    msg = componi_email_note_interne(note, ["it@example.com"])
    assert msg is not None
    assert msg.tipo == NOTE_INTERNE
    assert msg.oggetto.endswith("- DRA")
    assert msg.destinatari == ["it@example.com"]
    assert "Azure KO x3" in msg.corpo


def test_prepara_invii_include_note_interne_quando_presenti():
    d = _digest_con_aggiornamenti()
    d.note_interne.append(
        NotaInterna(tipo=TipoNotaInterna.sezione_a_zero_ripetuta, dettaglio="energia 0 x3")
    )
    invii = prepara_invii(d, CFG)
    tipi = [m.tipo for m in invii]
    assert tipi.count(NOTE_INTERNE) == 1
    assert len([t for t in tipi if t in (DIGEST_AGGIORNAMENTI, DIGEST_REMINDER)]) == 1


# --- invio (sender iniettato) -----------------------------------------------

def test_invia_tutti_usa_il_sender_iniettato():
    inviati = []
    n = invia_tutti(prepara_invii(digest_vuoto("2026-07-09"), CFG), inviati.append)
    assert n == 1
    assert len(inviati) == 1
