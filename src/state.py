"""Memoria persistente dell'agente: cosa è già stato riportato (dedup).

Usa un piccolo database SQLite. Serve a non riproporre, settimana dopo
settimana, voci già incluse in digest precedenti.

Note: il dedup è globale per URL (la colonna `beat` è salvata ma non usata nei
filtri). Non schedulare due esecuzioni sovrapposte sullo stesso database.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SeenStore:
    def __init__(self, path: str = "data/seen.sqlite3") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, beat TEXT, ts TEXT)"
        )
        self.conn.commit()

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

    def close(self) -> None:
        self.conn.close()
