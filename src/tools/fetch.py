"""Strumento di raccolta: legge le fonti (feed RSS/Atom) del beat.

Funziona sia con URL pubblici sia con file locali (utile per la demo offline).
Restituisce voci grezze; la selezione e la sintesi avvengono dopo.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict

import feedparser


@dataclass
class Candidate:
    titolo: str
    url: str
    fonte: str
    data: str
    estratto: str

    def to_dict(self) -> dict:
        return asdict(self)


def _pulisci(html: str) -> str:
    """Toglie i tag HTML basilari e normalizza gli spazi."""
    testo = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", testo).strip()


def fetch_candidates(cfg: dict) -> list[Candidate]:
    """Scarica le voci candidate da tutte le fonti definite in config."""
    out: list[Candidate] = []
    for fonte in cfg.get("fonti", []):
        try:
            feed = feedparser.parse(fonte["url"])
        except Exception as exc:  # rete, parsing, ...
            print(f"[attenzione] fonte non letta: {fonte['url']} ({exc})", file=sys.stderr)
            continue
        if getattr(feed, "bozo", 0) and not feed.entries:
            print(f"[attenzione] fonte non leggibile: {fonte['url']} "
                  f"({getattr(feed, 'bozo_exception', '?')})", file=sys.stderr)
            continue
        nome = fonte.get("nome") or feed.feed.get("title", fonte["url"])
        limite = int(fonte.get("max", 10))
        for e in feed.entries[:limite]:
            out.append(
                Candidate(
                    titolo=e.get("title", "").strip(),
                    url=e.get("link", "").strip(),
                    fonte=nome,
                    data=e.get("published", e.get("updated", "")),
                    estratto=_pulisci(e.get("summary", ""))[:500],
                )
            )
    return out
