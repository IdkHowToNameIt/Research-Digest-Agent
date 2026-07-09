"""Composizione e invio delle email settimanali (sez. 17).

Regole (17.1):
- si invia SEMPRE una sola email a settimana ai lettori: notifica se almeno una
  sezione ha aggiornamenti, altrimenti reminder. Mai entrambe, mai nessuna.
- l'oggetto termina sempre con "- DRA".
- la notifica rimanda alla homepage del sito, senza elencare tema/titolo/link.
- le note interne (se presenti) vanno in un'email SEPARATA al comparto IT (17.2).

La composizione (testata) e' separata dall'invio (I/O, provider deferito a 17.4):
`invia_tutti` accetta una callable `spedisci` iniettabile.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .schemas import Digest, NotaInterna, Stato

SUFFISSO_OGGETTO = "- DRA"

OGGETTO_REMINDER = "Nessun aggiornamento questa settimana - DRA"
CORPO_REMINDER = (
    "Questa settimana non sono emersi aggiornamenti rilevanti sui temi monitorati. "
    "Il prossimo digest arriva la settimana prossima."
)

# tipi di messaggio
DIGEST_AGGIORNAMENTI = "digest_aggiornamenti"
DIGEST_REMINDER = "digest_reminder"
NOTE_INTERNE = "note_interne"


@dataclass
class Messaggio:
    oggetto: str
    corpo: str
    destinatari: list[str]
    tipo: str


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


def prepara_invii(digest: Digest, cfg: dict) -> list[Messaggio]:
    """Prepara i messaggi da inviare per il run: sempre 1 email settimanale,
    piu' eventualmente 1 email di note interne."""
    email_cfg = cfg.get("email", {})
    homepage = cfg.get("sito", {}).get("homepage_url", "")
    invii = [
        componi_email_settimanale(
            digest, homepage, email_cfg.get("destinatari_digest", [])
        )
    ]
    nota = componi_email_note_interne(
        digest.note_interne, email_cfg.get("destinatari_note_interne", [])
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
    """Sender di default: stampa l'email invece di spedirla (provider SMTP reale
    rimandato, sez. 17.4). Utile per demo e sviluppo."""
    print(f"[email:{m.tipo}] a {', '.join(m.destinatari) or '(nessun destinatario)'}")
    print(f"  Oggetto: {m.oggetto}")
    for riga in m.corpo.splitlines() or [m.corpo]:
        print(f"  {riga}")
