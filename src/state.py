"""Memoria persistente dell'agente: storico degli articoli riportati.

Usa un piccolo database SQLite. Serve a:
- non riproporre voci già incluse in digest precedenti (dedup esatto per URL);
- alimentare il confronto fuzzy anti-duplicati nella finestra di 4-6 settimane
  (tabella `articoli`, con testo e timestamp — vedi src/tools/dedup.py, sez. 16.4).

Note: non schedulare due esecuzioni sovrapposte sullo stesso database.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class ArticoloArchiviato:
    """Voce di archivio usata dal confronto fuzzy."""
    hash: str
    url: str
    titolo_norm: str
    testo: str
    ts: str  # ISO 8601 UTC


class SeenStore:
    def __init__(self, path: str = "data/seen.sqlite3") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, beat TEXT, ts TEXT)"
        )
        # Storico ricco per il confronto fuzzy (sez. 16.4).
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS articoli ("
            "hash TEXT PRIMARY KEY, url TEXT, titolo_norm TEXT, testo TEXT, ts TEXT)"
        )
        self.conn.commit()

    # --- dedup esatto per URL (compat.) --------------------------------------
    def is_seen(self, url: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM seen WHERE url = ?", (url,))
        return cur.fetchone() is not None

    def mark_seen(self, url: str, beat: str = "") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen (url, beat, ts) VALUES (?, ?, ?)",
            (url, beat, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]

    # --- storico articoli per confronto fuzzy (sez. 16.4) --------------------
    def hash_esiste(self, h: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM articoli WHERE hash = ?", (h,))
        return cur.fetchone() is not None

    def registra_articolo(
        self, h: str, url: str, titolo_norm: str, testo: str, ts: str | None = None
    ) -> None:
        ts = ts or datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO articoli (hash, url, titolo_norm, testo, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (h, url, titolo_norm, testo, ts),
        )
        self.conn.commit()

    def articoli_recenti(
        self, ora: datetime | None = None, settimane: int = 6
    ) -> list[ArticoloArchiviato]:
        """Articoli archiviati entro `settimane` da `ora` (finestra fuzzy)."""
        ora = ora or datetime.now(timezone.utc)
        limite = (ora - timedelta(weeks=settimane)).isoformat()
        cur = self.conn.execute(
            "SELECT hash, url, titolo_norm, testo, ts FROM articoli "
            "WHERE ts >= ? ORDER BY ts DESC",
            (limite,),
        )
        return [ArticoloArchiviato(*row) for row in cur.fetchall()]

    def conta_articoli(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articoli").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
