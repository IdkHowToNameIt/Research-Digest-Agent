"""Test dell'email settimanale (Fase 7).

Basati sugli scenari Given/When/Then della sez. 17.1:
- notifica di aggiornamenti disponibili (oggetto termina in "- DRA", rimanda alla
  homepage, senza elencare tema/titolo/link);
- reminder quando tutte le sezioni sono "nessun_aggiornamento";
- esattamente un'email settimanale (mai entrambe, mai nessuna).
Piu' l'email separata di note interne (17.2).
"""
import pytest

from src.consegna.notifica import (
    CORPO_REMINDER,
    DIGEST_AGGIORNAMENTI,
    DIGEST_REMINDER,
    NOTE_INTERNE,
    OGGETTO_REMINDER,
    DestinatariNonConfigurati,
    HomepageNonConfigurata,
    Messaggio,
    attendi_fino_a,
    componi_email_note_interne,
    crea_sender,
    crea_sender_smtp,
    leggi_config_smtp,
    leggi_destinatari,
    leggi_homepage_url,
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
CFG = {"sito": {"homepage_url": HOMEPAGE}}
# I destinatari arrivano dall'ambiente, non dalla config (sono dati personali).
ENV = {
    "DIGEST_RECIPIENTS": "team@example.com",
    "INTERNAL_NOTES_RECIPIENTS": "it@example.com",
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
    invii = prepara_invii(_digest_con_aggiornamenti(), CFG, ENV)
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
    invii = prepara_invii(digest_vuoto("2026-07-09"), CFG, ENV)
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
        invii = prepara_invii(digest, CFG, ENV)
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
    invii = prepara_invii(d, CFG, ENV)
    tipi = [m.tipo for m in invii]
    assert tipi.count(NOTE_INTERNE) == 1
    assert len([t for t in tipi if t in (DIGEST_AGGIORNAMENTI, DIGEST_REMINDER)]) == 1


# --- destinatari dall'ambiente (fail-fast) ----------------------------------

def test_leggi_destinatari_separa_virgole_e_ripulisce():
    env = {"X": " a@x.com , b@y.com,c@z.com "}
    assert leggi_destinatari("X", env) == ["a@x.com", "b@y.com", "c@z.com"]


def test_leggi_destinatari_fail_fast_se_manca_o_vuota():
    for env in ({}, {"X": ""}, {"X": "   "}, {"X": " , "}):
        with pytest.raises(DestinatariNonConfigurati) as e:
            leggi_destinatari("X", env)
        assert "X" in str(e.value)   # l'errore nomina la variabile da impostare


def test_prepara_invii_fail_fast_senza_destinatari_digest():
    with pytest.raises(DestinatariNonConfigurati):
        prepara_invii(_digest_con_aggiornamenti(), CFG, {})


def test_note_interne_richiedono_il_proprio_secret_solo_se_ci_sono_note():
    # senza note il run non deve rompersi per un secret che non serve
    solo_digest = {"DIGEST_RECIPIENTS": "team@example.com"}
    invii = prepara_invii(digest_vuoto("2026-07-09"), CFG, solo_digest)
    assert len(invii) == 1
    # con note, invece, la lista IT e' obbligatoria
    d = _digest_con_aggiornamenti()
    d.note_interne.append(
        NotaInterna(tipo=TipoNotaInterna.sezione_a_zero_ripetuta, dettaglio="energia 0 x3")
    )
    with pytest.raises(DestinatariNonConfigurati):
        prepara_invii(d, CFG, solo_digest)


def test_note_interne_non_vanno_ai_lettori_del_digest():
    """16.7/17.2: le due liste restano separate, nessuna sovrapposizione."""
    d = _digest_con_aggiornamenti()
    d.note_interne.append(
        NotaInterna(tipo=TipoNotaInterna.fetch_failed_ripetuto, dettaglio="Azure KO x3")
    )
    invii = prepara_invii(d, CFG, ENV)
    note = [m for m in invii if m.tipo == NOTE_INTERNE][0]
    settimanale = [m for m in invii if m.tipo == DIGEST_AGGIORNAMENTI][0]
    assert note.destinatari == ["it@example.com"]
    assert "team@example.com" not in note.destinatari
    assert "Azure KO x3" not in settimanale.corpo


# --- homepage: env ha la precedenza sul config ------------------------------

def test_homepage_da_config_se_env_non_la_sovrascrive():
    assert leggi_homepage_url(CFG, {}) == HOMEPAGE


def test_homepage_da_env_vince_sul_config():
    env = {"HOMEPAGE_URL": "https://sito-del-cliente.example"}
    assert leggi_homepage_url(CFG, env) == "https://sito-del-cliente.example"


def test_homepage_env_vuota_o_spazi_ricade_sul_config():
    for env in ({"HOMEPAGE_URL": ""}, {"HOMEPAGE_URL": "   "}):
        assert leggi_homepage_url(CFG, env) == HOMEPAGE


def test_homepage_fail_fast_se_manca():
    for cfg in ({}, {"sito": {}}, {"sito": {"homepage_url": ""}}):
        with pytest.raises(HomepageNonConfigurata):
            leggi_homepage_url(cfg, {})


def test_homepage_fail_fast_sul_placeholder_del_repo():
    """Il placeholder non deve passare silenziosamente: finirebbe nell'email."""
    cfg = {"sito": {"homepage_url": "https://DA-SOSTITUIRE.example.com"}}
    with pytest.raises(HomepageNonConfigurata):
        leggi_homepage_url(cfg, {})
    # ...ma la variabile d'ambiente lo sovrascrive senza toccare il config
    assert leggi_homepage_url(cfg, {"HOMEPAGE_URL": "https://vero.example"}) \
        == "https://vero.example"


def test_prepara_invii_usa_la_homepage_dell_ambiente():
    env = dict(ENV, HOMEPAGE_URL="https://sito-del-cliente.example")
    invii = prepara_invii(_digest_con_aggiornamenti(), CFG, env)
    msg = [m for m in invii if m.tipo == DIGEST_AGGIORNAMENTI][0]
    assert "https://sito-del-cliente.example" in msg.corpo
    assert HOMEPAGE not in msg.corpo


# --- attesa dell'orario di invio --------------------------------------------

def _alle(hh, mm):
    from datetime import datetime, timezone
    return lambda: datetime(2026, 7, 20, hh, mm, tzinfo=timezone.utc)


def test_attende_fino_all_orario_richiesto():
    dormite = []
    atteso = attendi_fino_a("06:30", adesso=_alle(5, 40), dormi=dormite.append)
    assert atteso == 50 * 60          # 05:40 -> 06:30
    assert dormite == [50 * 60]


def test_non_attende_se_l_orario_e_gia_passato():
    """Run in ritardo: le email partono subito, non il lunedì dopo."""
    dormite = []
    assert attendi_fino_a("06:30", adesso=_alle(6, 45), dormi=dormite.append) == 0
    assert dormite == []


def test_non_attende_oltre_il_tetto_massimo():
    """Avvio manuale a notte fonda: non si blocca il runner per ore."""
    dormite = []
    assert attendi_fino_a("06:30", adesso=_alle(0, 10), dormi=dormite.append) == 0
    assert dormite == []


def test_nessuna_attesa_senza_orario_o_con_orario_invalido():
    dormite = []
    for orario in (None, "", "non-un-orario", "25:99"):
        assert attendi_fino_a(orario, adesso=_alle(5, 40), dormi=dormite.append) == 0
    assert dormite == []


# --- invio (sender iniettato) -----------------------------------------------

def test_invia_tutti_usa_il_sender_iniettato():
    inviati = []
    n = invia_tutti(prepara_invii(digest_vuoto("2026-07-09"), CFG, ENV), inviati.append)
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
