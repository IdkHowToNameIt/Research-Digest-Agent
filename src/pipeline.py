"""Orchestrazione della pipeline (~80% script, modello solo per la sintesi).

fetch -> deduplica -> classifica/raggruppa -> note interne -> sintesi -> Digest.
Deterministica e testabile: fonti via parser iniettabile, modello via `genera`
iniettabile (o None per la modalita' demo).
"""
from __future__ import annotations

from datetime import datetime, timezone

import feedparser

from .raccolta.classify import raggruppa_per_tema
from .consegna.note_interne import aggiorna_e_genera_note
from .schemas import Digest, Tema
from .modello.sintesi import Generatore, assembla_digest
from .state import SeenStore
from .raccolta.dedup import deduplica, registra_pubblicati
from .raccolta.fetch import fetch_tutte


def costruisci_digest(
    cfg: dict,
    genera: Generatore | None = None,
    *,
    store: SeenStore | None = None,
    ora: datetime | None = None,
    parse=feedparser.parse,
) -> Digest:
    """Esegue un run completo e restituisce il Digest (5 sezioni fisse)."""
    ora = ora or datetime.now(timezone.utc)
    store_proprio = store is None
    store = store or SeenStore(cfg.get("db_path", "data/seen.sqlite3"))
    try:
        esiti = fetch_tutte(cfg, parse=parse)
        candidati = [c for e in esiti for c in e.candidati]

        tenuti, _ = deduplica(
            candidati, store,
            soglia=cfg.get("soglia_overlap_dedup", 0.7),
            finestra_settimane=cfg.get("finestra_dedup_settimane", 6),
            ora=ora,
        )

        gruppi, _scartati = raggruppa_per_tema(tenuti)
        conteggi = {t: len(v) for t, v in gruppi.items()}
        note = aggiorna_e_genera_note(store, esiti, conteggi)

        digest = assembla_digest(
            gruppi, genera,
            data_generazione=ora.date().isoformat(),
            note_interne=note,
        )

        # Archivia solo gli articoli effettivamente pubblicati (per i run futuri).
        pubblicati = [c for v in gruppi.values() for c in v]
        registra_pubblicati(pubblicati, store)
        return digest
    finally:
        if store_proprio:
            store.close()
