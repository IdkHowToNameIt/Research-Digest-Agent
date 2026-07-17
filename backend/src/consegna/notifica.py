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
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable

from ..schemas import Digest, NotaInterna, Stato

SUFFISSO_OGGETTO = "- DRA"

# Variabili d'ambiente con i destinatari (liste separate da virgola).
ENV_DESTINATARI_DIGEST = "DIGEST_RECIPIENTS"
ENV_DESTINATARI_NOTE_INTERNE = "INTERNAL_NOTES_RECIPIENTS"

OGGETTO_REMINDER = "Nessun aggiornamento questa settimana - DRA"
CORPO_REMINDER = (
    "Questa settimana non sono emersi aggiornamenti rilevanti sui temi monitorati. "
    "Il prossimo digest arriva la settimana prossima."
)

# tipi di messaggio
DIGEST_AGGIORNAMENTI = "digest_aggiornamenti"
DIGEST_REMINDER = "digest_reminder"
NOTE_INTERNE = "note_interne"


class DestinatariNonConfigurati(RuntimeError):
    """Sollevata quando manca la lista destinatari di un'email da spedire."""


@dataclass
class Messaggio:
    oggetto: str
    corpo: str
    destinatari: list[str]
    tipo: str


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
        oggetto = f"Il digest di questa settimana è pronto {SUFFISSO_OGGETTO}"
        corpo = (
            "Sono disponibili nuovi aggiornamenti sui temi monitorati. "
            f"Visita la homepage per leggerli: {homepage_url}"
        )
        return Messaggio(oggetto, corpo, list(destinatari), DIGEST_AGGIORNAMENTI)
    return Messaggio(OGGETTO_REMINDER, CORPO_REMINDER, list(destinatari), DIGEST_REMINDER)


def componi_email_note_interne(
    note_interne: list[NotaInterna], destinatari: list[str]
) -> Messaggio | None:
    """Email separata al comparto IT, solo se ci sono note (17.2). Altrimenti None."""
    if not note_interne:
        return None
    corpo = "Segnalazioni operative del Research Digest Agent:\n\n" + "\n".join(
        f"- [{n.tipo.value}] {n.dettaglio}" for n in note_interne
    )
    return Messaggio(f"Note interne DRA {SUFFISSO_OGGETTO}", corpo, list(destinatari), NOTE_INTERNE)


def prepara_invii(digest: Digest, cfg: dict, env: dict | None = None) -> list[Messaggio]:
    """Prepara i messaggi da inviare per il run: sempre 1 email settimanale,
    piu' eventualmente 1 email di note interne.

    I destinatari arrivano dall'ambiente, non da `cfg`. INTERNAL_NOTES_RECIPIENTS
    e' richiesto solo quando ci sono davvero note da spedire: le note interne sono
    rare e un run senza note non deve fallire per un secret che non gli serve.
    """
    env = os.environ if env is None else env
    homepage = cfg.get("sito", {}).get("homepage_url", "")
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
