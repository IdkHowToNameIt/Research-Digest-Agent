"""Strumento di raccolta: legge le fonti (feed RSS/Atom) del beat.

Rispetto allo starter, distingue esplicitamente due esiti per fonte (sez. 16.1):
- STATO_OK: la richiesta e' riuscita (anche con 0 voci) -> candidati raccolti.
- STATO_FETCH_FAILED: eccezione, timeout, errore HTTP o feed malformato.
Questa distinzione e' indispensabile perche' un feed rotto non risulti
indistinguibile da un feed semplicemente silenzioso (16.1). Il conteggio dei run
consecutivi falliti e la nota interna sono in una fase successiva (Fase 5).

Il troncamento degli estratti e' differenziato per fonte (sez. 13): alcune fonti
non hanno limite (arXiv, Google Cloud Blog, Google Cloud — Infrastructure), le
altre a 500 caratteri tagliati su confine di parola (mai a meta' parola, 16.2).

`feedparser.parse` accetta URL http, percorsi di file locali e stringhe: per i
test si inietta un parser finto tramite il parametro `parse`, senza rete.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

import feedparser

STATO_OK = "ok"
STATO_FETCH_FAILED = "fetch_failed"


@dataclass
class Candidato:
    titolo: str
    url: str
    fonte: str          # nome della fonte
    tema: str           # sotto-tema primario della fonte (hint; classificazione in Fase 3)
    data: str
    estratto: str

    def to_dict(self) -> dict:
        return {
            "titolo": self.titolo,
            "url": self.url,
            "fonte": self.fonte,
            "tema": self.tema,
            "data": self.data,
            "estratto": self.estratto,
        }


@dataclass
class EsitoFonte:
    """Esito del fetch di una singola fonte in un run."""
    nome: str
    stato: str                       # STATO_OK | STATO_FETCH_FAILED
    candidati: list[Candidato] = field(default_factory=list)
    errore: str | None = None

    @property
    def ok(self) -> bool:
        return self.stato == STATO_OK

    @property
    def zero_voci(self) -> bool:
        """True se il fetch e' riuscito ma il feed non aveva voci."""
        return self.stato == STATO_OK and not self.candidati


def _pulisci(html: str) -> str:
    """Toglie i tag HTML basilari e normalizza gli spazi."""
    testo = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", testo).strip()


def tronca_su_parola(testo: str, limite: int | None) -> str:
    """Tronca `testo` a `limite` caratteri su confine di parola (mai a meta'
    parola, 16.2). `limite=None` -> nessun troncamento. Risultato sempre <= limite.
    """
    if limite is None or len(testo) <= limite:
        return testo
    taglio = testo[:limite]
    # se il carattere subito dopo il taglio non e' uno spazio, siamo a meta'
    # parola: si retrocede all'ultimo spazio.
    if limite < len(testo) and not testo[limite].isspace():
        spazio = taglio.rfind(" ")
        if spazio > 0:
            taglio = taglio[:spazio]
    return taglio.rstrip()


def _parse_feed(url: str, parse):
    """Esegue il parsing; solleva se il feed e' irrecuperabile (bozo senza voci)."""
    feed = parse(url)
    if getattr(feed, "bozo", 0) and not getattr(feed, "entries", None):
        raise ValueError(str(getattr(feed, "bozo_exception", "feed malformato")))
    return feed


def fetch_fonte(fonte: dict, parse=feedparser.parse) -> EsitoFonte:
    """Legge una singola fonte e ne restituisce l'esito (fail-soft: non solleva)."""
    nome = fonte.get("nome") or fonte.get("url", "?")
    try:
        feed = _parse_feed(fonte["url"], parse)
    except Exception as exc:  # rete, HTTP, parsing, feed malformato...
        print(f"[attenzione] fonte non letta: {nome} ({exc})", file=sys.stderr)
        return EsitoFonte(nome=nome, stato=STATO_FETCH_FAILED, errore=str(exc))

    tema = fonte.get("tema", "")
    limite = fonte.get("troncamento", 500)
    mx = fonte.get("max")
    voci = feed.entries if mx is None else feed.entries[: int(mx)]

    candidati: list[Candidato] = []
    for e in voci:
        estratto = tronca_su_parola(_pulisci(e.get("summary", "")), limite)
        candidati.append(
            Candidato(
                titolo=e.get("title", "").strip(),
                url=e.get("link", "").strip(),
                fonte=nome,
                tema=tema,
                data=e.get("published", e.get("updated", "")),
                estratto=estratto,
            )
        )
    return EsitoFonte(nome=nome, stato=STATO_OK, candidati=candidati)


def fetch_tutte(cfg: dict, parse=feedparser.parse) -> list[EsitoFonte]:
    """Legge tutte le fonti del config (fail-soft: una fonte KO non blocca le altre)."""
    return [fetch_fonte(fonte, parse=parse) for fonte in cfg.get("fonti", [])]


def fetch_candidates(cfg: dict, parse=feedparser.parse) -> list[Candidato]:
    """Compatibilita': lista piatta dei soli candidati raccolti (fonti OK)."""
    out: list[Candidato] = []
    for esito in fetch_tutte(cfg, parse=parse):
        out.extend(esito.candidati)
    return out
