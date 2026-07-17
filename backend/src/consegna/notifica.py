"""Composizione e invio delle email settimanali (sez. 17).

Regole (17.1):
- si invia SEMPRE una sola email a settimana ai lettori: notifica se almeno una
  sezione ha aggiornamenti, altrimenti reminder. Mai entrambe, mai nessuna.
- l'oggetto termina sempre con "- DRA".
- la notifica rimanda alla homepage del sito, senza elencare tema/titolo/link.
- le note interne (se presenti) vanno in un'email SEPARATA al comparto IT (17.2).

I destinatari NON stanno nel repo: si leggono da due variabili d'ambiente distinte
(`DIGEST_RECIPIENTS`, `INTERNAL_NOTES_RECIPIENTS`), cosi' chi adotta il repo li
configura nel proprio account senza toccare il codice. Restano due liste separate
apposta: le note interne non devono mai raggiungere i lettori del digest (16.7/17.2).

La composizione (testata) e' separata dall'invio (I/O): `invia_tutti` accetta una
callable `spedisci` iniettabile. Sender disponibili:
- `spedisci_console`: stampa l'email (sviluppo locale, nessuna credenziale);
- sender SMTP reale (`crea_sender_smtp`, Gmail di default) selezionato in automatico
  da `crea_sender` quando sono presenti le credenziali SMTP (sez. 17.4).
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Callable

from ..schemas import Digest, NotaInterna, Stato

SUFFISSO_OGGETTO = "- DRA"

# Variabili d'ambiente con i destinatari (liste separate da virgola).
ENV_DESTINATARI_DIGEST = "DIGEST_RECIPIENTS"
ENV_DESTINATARI_NOTE_INTERNE = "INTERNAL_NOTES_RECIPIENTS"

# URL pubblico del sito: se impostato, ha la precedenza su sito.homepage_url del
# config. E' configurazione del singolo deployment, non del progetto.
ENV_HOMEPAGE_URL = "HOMEPAGE_URL"
# Segnale che nel config c'e' ancora il placeholder di repo, mai sostituito.
PLACEHOLDER_HOMEPAGE = "DA-SOSTITUIRE"

OGGETTO_REMINDER = f"Questa settimana è tranquilla {SUFFISSO_OGGETTO}"
CORPO_REMINDER = (
    "Ciao!\n\n"
    "Questa settimana sui temi che seguiamo non è emerso nulla di davvero "
    "rilevante, quindi non c'è un nuovo digest da leggere — e va benissimo così: "
    "ti scriviamo solo quando c'è qualcosa che vale la pena.\n\n"
    "Ci risentiamo la settimana prossima!\n\n"
    "A presto,\n"
    "il team del Research Digest Agent"
)

# tipi di messaggio
DIGEST_AGGIORNAMENTI = "digest_aggiornamenti"
DIGEST_REMINDER = "digest_reminder"
NOTE_INTERNE = "note_interne"


class DestinatariNonConfigurati(RuntimeError):
    """Sollevata quando manca la lista destinatari di un'email da spedire."""


class HomepageNonConfigurata(RuntimeError):
    """Sollevata quando l'URL pubblico del sito manca o e' ancora il placeholder."""


@dataclass
class Messaggio:
    oggetto: str
    corpo: str
    destinatari: list[str]
    tipo: str


def leggi_homepage_url(cfg: dict, env: dict | None = None) -> str:
    """URL pubblico del sito, con precedenza a HOMEPAGE_URL sul config.

    Fail-fast anche sul placeholder di repo: un'email che invita a leggere il
    digest su un link finto e' peggio di un run fallito, perche' nessuno se ne
    accorge finche' non la apre un lettore.
    """
    env = os.environ if env is None else env
    da_env = (env.get(ENV_HOMEPAGE_URL) or "").strip()
    url = da_env or str(cfg.get("sito", {}).get("homepage_url") or "").strip()
    if not url or PLACEHOLDER_HOMEPAGE in url:
        raise HomepageNonConfigurata(
            "Manca l'URL pubblico del sito: imposta la variabile "
            f"{ENV_HOMEPAGE_URL} (su GitHub: Settings > Secrets and variables > "
            "Actions > scheda Variables) oppure il campo sito.homepage_url in "
            "config.yaml. E' il link che l'email settimanale manda ai lettori."
        )
    return url


def leggi_destinatari(nome_var: str, env: dict | None = None) -> list[str]:
    """Legge una lista di destinatari da una variabile d'ambiente (separati da
    virgola). Fail-fast: mai un default silenzioso, perche' un digest spedito a
    nessuno passerebbe inosservato.
    """
    env = os.environ if env is None else env
    indirizzi = [x.strip() for x in (env.get(nome_var) or "").split(",") if x.strip()]
    if not indirizzi:
        raise DestinatariNonConfigurati(
            f"Manca la lista destinatari: imposta {nome_var} con gli indirizzi "
            "separati da virgola (in locale nel file .env, in produzione come "
            "secret di GitHub Actions)."
        )
    return indirizzi


def ci_sono_aggiornamenti(digest: Digest) -> bool:
    return any(s.stato is Stato.con_aggiornamenti for s in digest.sezioni)


def componi_email_settimanale(
    digest: Digest, homepage_url: str, destinatari: list[str]
) -> Messaggio:
    """L'unica email settimanale ai lettori: notifica oppure reminder."""
    if ci_sono_aggiornamenti(digest):
        oggetto = f"Il tuo digest della settimana è pronto {SUFFISSO_OGGETTO}"
        corpo = (
            "Ciao!\n\n"
            "Il Research Digest di questa settimana è pronto. Abbiamo dato "
            "un'occhiata alle fonti su Infrastruttura & Hardware AI e raccolto "
            "per te gli aggiornamenti che vale davvero la pena leggere.\n\n"
            f"Lo trovi qui: {homepage_url}\n\n"
            "Buona lettura,\n"
            "il team del Research Digest Agent"
        )
        return Messaggio(oggetto, corpo, list(destinatari), DIGEST_AGGIORNAMENTI)
    return Messaggio(OGGETTO_REMINDER, CORPO_REMINDER, list(destinatari), DIGEST_REMINDER)


def componi_email_note_interne(
    note_interne: list[NotaInterna], destinatari: list[str]
) -> Messaggio | None:
    """Email separata al comparto IT, solo se ci sono note (17.2). Altrimenti None."""
    if not note_interne:
        return None
    corpo = (
        "Ciao,\n\n"
        "un paio di cose dal Research Digest Agent che varrebbe la pena controllare "
        "quando hai un momento:\n\n"
        + "\n".join(f"- [{n.tipo.value}] {n.dettaglio}" for n in note_interne)
        + "\n\nNiente di bloccante: il digest è uscito regolarmente, sono solo "
        "segnalazioni da tenere d'occhio.\n\n"
        "Grazie,\n"
        "il team del Research Digest Agent"
    )
    return Messaggio(f"Note interne {SUFFISSO_OGGETTO}", corpo, list(destinatari), NOTE_INTERNE)


def prepara_invii(digest: Digest, cfg: dict, env: dict | None = None) -> list[Messaggio]:
    """Prepara i messaggi da inviare per il run: sempre 1 email settimanale,
    piu' eventualmente 1 email di note interne.

    I destinatari arrivano dall'ambiente, non da `cfg`. INTERNAL_NOTES_RECIPIENTS
    e' richiesto solo quando ci sono davvero note da spedire: le note interne sono
    rare e un run senza note non deve fallire per un secret che non gli serve.
    """
    env = os.environ if env is None else env
    homepage = leggi_homepage_url(cfg, env)
    invii = [
        componi_email_settimanale(
            digest, homepage, leggi_destinatari(ENV_DESTINATARI_DIGEST, env)
        )
    ]
    if digest.note_interne:
        nota = componi_email_note_interne(
            digest.note_interne,
            leggi_destinatari(ENV_DESTINATARI_NOTE_INTERNE, env),
        )
        if nota is not None:
            invii.append(nota)
    return invii


def invia_tutti(messaggi: list[Messaggio], spedisci: Callable[[Messaggio], None]) -> int:
    """Invia i messaggi tramite la callable `spedisci` (iniettabile/mockabile).
    Ritorna il numero di email inviate."""
    for m in messaggi:
        spedisci(m)
    return len(messaggi)


def spedisci_console(m: Messaggio) -> None:
    """Sender di sviluppo: stampa l'email invece di spedirla (nessuna credenziale).
    Usato in locale e come fallback quando SMTP non e' configurato."""
    print(f"[email:{m.tipo}] a {', '.join(m.destinatari) or '(nessun destinatario)'}")
    print(f"  Oggetto: {m.oggetto}")
    for riga in m.corpo.splitlines() or [m.corpo]:
        print(f"  {riga}")


# --- attesa dell'orario di invio --------------------------------------------

# Oltre questa attesa non si aspetta: significa che il run non e' quello
# schedulato (es. avvio manuale a meta' giornata) e bloccare il runner per ore
# sarebbe assurdo.
ATTESA_MASSIMA_MINUTI = 90


def attendi_fino_a(
    orario_utc: str | None,
    adesso: Callable[[], datetime] | None = None,
    dormi: Callable[[float], None] = time.sleep,
    attesa_massima_minuti: int = ATTESA_MASSIMA_MINUTI,
) -> int:
    """Attende fino a `orario_utc` ("HH:MM", UTC) di oggi. Ritorna i secondi attesi.

    Non attende (ritorna 0) se l'orario e' gia' passato o se manca piu' di
    `attesa_massima_minuti`. L'orario e' in UTC perche' e' la stessa base di
    tempo del cron di GitHub Actions: nessuna sorpresa col cambio d'ora.

    `adesso`/`dormi` sono iniettabili per i test (nessuna attesa reale).
    """
    if not orario_utc:
        return 0
    ora_corrente = (adesso or (lambda: datetime.now(timezone.utc)))()
    try:
        ore, minuti = (int(x) for x in orario_utc.split(":"))
        obiettivo = ora_corrente.replace(hour=ore, minute=minuti, second=0, microsecond=0)
    except (ValueError, TypeError):
        print(f"[attesa] orario non valido ({orario_utc!r}), atteso HH:MM: invio subito.",
              file=sys.stderr)
        return 0

    secondi = int((obiettivo - ora_corrente).total_seconds())
    if secondi <= 0:
        return 0
    if secondi > attesa_massima_minuti * 60:
        print(f"[attesa] a {orario_utc} UTC mancano piu' di {attesa_massima_minuti} "
              f"minuti: non e' il run schedulato, invio subito.", file=sys.stderr)
        return 0
    print(f"[attesa] invio email rimandato alle {orario_utc} UTC "
          f"({secondi // 60} min).")
    dormi(secondi)
    return secondi


# --- invio SMTP reale (Gmail di default), sez. 17.4 -------------------------

@dataclass
class ConfigSMTP:
    host: str
    port: int
    user: str
    password: str
    mittente: str  # header From (default = user)


def leggi_config_smtp(env: dict | None = None) -> ConfigSMTP | None:
    """Legge la config SMTP dalle variabili d'ambiente. Ritorna None se mancano le
    credenziali (SMTP_USER + SMTP_PASS), cosi' il chiamante ricade sulla console.

    Gmail: host=smtp.gmail.com, port=587 (STARTTLS), user=indirizzo@gmail.com,
    password = **App Password** a 16 cifre (richiede la 2FA sull'account Google;
    la normale password dell'account NON funziona con SMTP).
    """
    env = os.environ if env is None else env
    user = (env.get("SMTP_USER") or "").strip()
    password = (env.get("SMTP_PASS") or "").strip()
    if not user or not password:
        return None
    return ConfigSMTP(
        host=(env.get("SMTP_HOST") or "smtp.gmail.com").strip(),
        port=int(env.get("SMTP_PORT") or "587"),
        user=user,
        password=password,
        mittente=(env.get("SMTP_FROM") or user).strip(),
    )


def componi_mime(m: Messaggio, mittente: str) -> EmailMessage:
    """Costruisce il messaggio MIME (testo semplice) da un Messaggio."""
    msg = EmailMessage()
    msg["Subject"] = m.oggetto
    msg["From"] = mittente
    msg["To"] = ", ".join(m.destinatari)
    msg.set_content(m.corpo)
    return msg


def crea_sender_smtp(
    cfg: ConfigSMTP,
    connetti: Callable[[], smtplib.SMTP] | None = None,
) -> Callable[[Messaggio], None]:
    """Crea un sender che spedisce via SMTP secondo `cfg`.

    `connetti` e' iniettabile per i test (deve ritornare un oggetto SMTP usabile
    come context manager). Di default apre una connessione reale: STARTTLS su
    porta 587, SMTP_SSL su porta 465.
    """
    usa_ssl = cfg.port == 465

    def _connetti_reale() -> smtplib.SMTP:
        if usa_ssl:
            return smtplib.SMTP_SSL(cfg.host, cfg.port,
                                    context=ssl.create_default_context())
        return smtplib.SMTP(cfg.host, cfg.port)

    apri = connetti or _connetti_reale

    def spedisci(m: Messaggio) -> None:
        if not m.destinatari:
            print(f"[email:{m.tipo}] nessun destinatario: invio saltato.",
                  file=sys.stderr)
            return
        msg = componi_mime(m, cfg.mittente)
        with apri() as server:
            if not usa_ssl:
                server.starttls(context=ssl.create_default_context())
            server.login(cfg.user, cfg.password)
            server.send_message(msg)
        print(f"[email:{m.tipo}] inviata a {', '.join(m.destinatari)}")

    return spedisci


def crea_sender(env: dict | None = None) -> Callable[[Messaggio], None]:
    """Sceglie il sender: SMTP reale se le credenziali sono presenti, altrimenti
    la console (con avviso). Usato da main.py."""
    cfg = leggi_config_smtp(env)
    if cfg is None:
        print("[email] SMTP non configurato (manca SMTP_USER/SMTP_PASS): "
              "le email vengono solo stampate.", file=sys.stderr)
        return spedisci_console
    print(f"[email] invio SMTP attivo via {cfg.host}:{cfg.port} (da {cfg.mittente}).",
          file=sys.stderr)
    return crea_sender_smtp(cfg)
