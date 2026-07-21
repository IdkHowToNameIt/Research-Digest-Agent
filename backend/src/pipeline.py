"""Orchestrazione della pipeline (~80% script, modello solo per la sintesi).

fetch -> deduplica -> classifica/raggruppa -> note interne -> sintesi -> Digest.
Deterministica e testabile: fonti via parser iniettabile, modello via `genera`
iniettabile (o None per la modalita' demo).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import feedparser

if TYPE_CHECKING:
    from .metriche import RaccoltaMetriche

from .raccolta.classify import raggruppa_per_tema
from .consegna.note_interne import aggiorna_e_genera_note
from .schemas import Digest, Tema
from .modello.sintesi import Generatore, assembla_digest
from .state import SeenStore
from .raccolta.dedup import collassa_storie, deduplica, registra_pubblicati
from .raccolta.fetch import fetch_tutte


def costruisci_digest(
    cfg: dict,
    genera: Generatore | None = None,
    *,
    store: SeenStore | None = None,
    ora: datetime | None = None,
    parse=feedparser.parse,
    metriche: "RaccoltaMetriche | None" = None,
) -> Digest:
    """Esegue un run completo e restituisce il Digest (5 sezioni fisse).

    Se `metriche` è fornita, vi registra le metriche OPERATIVE del run (stato
    fonti, statistiche dedup, copertura): dati che altrimenti la pipeline calcola
    e scarta. L'uso di token arriva invece dal generatore (callback separata).
    """
    ora = ora or datetime.now(timezone.utc)
    store_proprio = store is None
    store = store or SeenStore(cfg.get("db_path", "data/seen.sqlite3"))
    try:
        esiti = fetch_tutte(cfg, parse=parse)
        candidati = [c for e in esiti for c in e.candidati]

        # Prima del dedup, e quindi prima di spendere chiamate al modello: sulle
        # fonti aggregate (piu' testate, una notizia) il dedup fuzzy non funziona
        # per costruzione, vedi sez. 24. Qui si tiene una voce per storia.
        aggregatori = {
            f["nome"] for f in cfg.get("fonti", []) if f.get("aggregatore")
        }
        # `candidati` resta la lista GREZZA: le metriche documentano `raccolti`
        # come "candidati totali dalle fonti", e riassegnarla falserebbe il dato.
        utili = candidati
        if aggregatori:
            utili, _varianti = collassa_storie(candidati, aggregatori)
        accorpati = len(candidati) - len(utili)

        tenuti, esiti_dedup = deduplica(
            utili, store,
            soglia=cfg.get("soglia_overlap_dedup", 0.7),
            finestra_settimane=cfg.get("finestra_dedup_settimane", 6),
            ora=ora,
        )

        gruppi, scartati = raggruppa_per_tema(tenuti)
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

        if metriche is not None:
            # Dopo le note (i contatori consecutivi sono aggiornati) e dopo aver
            # assemblato il digest (stato per tema disponibile).
            metriche.registra_run(
                candidati=candidati,
                esiti_fonti=esiti,
                esiti_dedup=esiti_dedup,
                scartati_classificazione=len(scartati),
                pubblicati=len(pubblicati),
                digest=digest,
                store=store,
                accorpati_aggregatore=accorpati,
            )
        return digest
    finally:
        if store_proprio:
            store.close()
