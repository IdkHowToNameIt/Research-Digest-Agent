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
    Messaggio,
    componi_email_note_interne,
    crea_sender,
    crea_sender_smtp,
    leggi_config_smtp,
    invia_tutti,
    prepara_invii,
    spedisci_console,
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


# --- invio SMTP reale (sez. 17.4) -------------------------------------------

class FakeSMTP:
    """Doppio di test per smtplib.SMTP: registra le chiamate, non apre connessioni."""
    def __init__(self):
        self.starttls_chiamato = False
        self.login_args = None
        self.inviati = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.starttls_chiamato = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.inviati.append(msg)


def _cfg_smtp(**kw):
    base = dict(host="smtp.gmail.com", port=587, user="me@gmail.com",
                password="app-pw", mittente="me@gmail.com")
    base.update(kw)
    return leggi_config_smtp({
        "SMTP_HOST": base["host"], "SMTP_PORT": str(base["port"]),
        "SMTP_USER": base["user"], "SMTP_PASS": base["password"],
        "SMTP_FROM": base["mittente"],
    })


def test_leggi_config_smtp_default_gmail():
    assert leggi_config_smtp({}) is None
    assert leggi_config_smtp({"SMTP_USER": "u"}) is None          # manca la password
    assert leggi_config_smtp({"SMTP_PASS": "p"}) is None          # manca l'utente
    cfg = leggi_config_smtp({"SMTP_USER": "u@gmail.com", "SMTP_PASS": "pw"})
    assert cfg.host == "smtp.gmail.com" and cfg.port == 587
    assert cfg.user == "u@gmail.com" and cfg.mittente == "u@gmail.com"


def test_sender_smtp_starttls_login_e_invio():
    fake = FakeSMTP()
    sender = crea_sender_smtp(_cfg_smtp(), connetti=lambda: fake)
    m = Messaggio("Oggetto - DRA", "Corpo\nseconda riga",
                  ["a@x.com", "b@y.com"], DIGEST_AGGIORNAMENTI)
    sender(m)
    assert fake.starttls_chiamato is True
    assert fake.login_args == ("me@gmail.com", "app-pw")
    assert len(fake.inviati) == 1
    msg = fake.inviati[0]
    assert msg["Subject"] == "Oggetto - DRA"
    assert msg["From"] == "me@gmail.com"
    assert msg["To"] == "a@x.com, b@y.com"
    assert "seconda riga" in msg.get_content()


def test_sender_smtp_porta_465_usa_ssl_senza_starttls():
    fake = FakeSMTP()
    sender = crea_sender_smtp(_cfg_smtp(port=465), connetti=lambda: fake)
    sender(Messaggio("o", "c", ["a@x.com"], DIGEST_REMINDER))
    assert fake.starttls_chiamato is False   # su 465 la cifratura è già a livello di socket
    assert len(fake.inviati) == 1


def test_sender_smtp_senza_destinatari_non_invia():
    fake = FakeSMTP()
    sender = crea_sender_smtp(_cfg_smtp(), connetti=lambda: fake)
    sender(Messaggio("o", "c", [], DIGEST_REMINDER))
    assert fake.inviati == [] and fake.login_args is None


def test_crea_sender_fallback_console_e_smtp():
    assert crea_sender({}) is spedisci_console               # niente credenziali -> console
    sender = crea_sender({"SMTP_USER": "u@gmail.com", "SMTP_PASS": "pw"})
    assert callable(sender) and sender is not spedisci_console  # credenziali -> SMTP
