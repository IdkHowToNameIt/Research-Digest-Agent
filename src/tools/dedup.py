"""Filtro anti-duplicati: rimuove le voci già viste e quelle ripetute nella
stessa esecuzione."""
from __future__ import annotations

from .fetch import Candidato
from ..state import SeenStore


def filtra_nuove(candidati: list[Candidato], store: SeenStore) -> list[Candidato]:
    visti_in_run: set[str] = set()
    nuove: list[Candidate] = []
    for c in candidati:
        if not c.url or c.url in visti_in_run:
            continue
        if store.is_seen(c.url):
            continue
        visti_in_run.add(c.url)
        nuove.append(c)
    return nuove
