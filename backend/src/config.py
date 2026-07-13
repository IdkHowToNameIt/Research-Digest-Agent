"""Caricamento e validazione della configurazione (config.yaml).

Oltre alla validazione minima dello starter, verifica i campi introdotti per il
beat "Infrastruttura & Hardware AI": tema (enum), troncamento per fonte, ecc.
Riferimento: Notion sez. 11 (fonti) e 13 (troncamento).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import Tema

# Default globali.
_DEFAULT_TRONCAMENTO = 500
_TEMI_VALIDI = {t.value for t in Tema}


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path).resolve()
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    if not cfg.get("beat"):
        raise ValueError(f"In {config_path.name} manca il campo obbligatorio 'beat'.")
    fonti = cfg.get("fonti")
    if not fonti:
        raise ValueError(f"In {config_path.name} serve almeno una fonte sotto 'fonti'.")

    base = config_path.parent
    for i, fonte in enumerate(fonti):
        nome = fonte.get("nome") or f"(fonte #{i + 1})"
        url = str(fonte.get("url", ""))
        if not url:
            raise ValueError(f"La fonte '{nome}' non ha un 'url'.")

        # Tema obbligatorio e vincolato all'enum (coerenza con le 5 sezioni fisse).
        tema = fonte.get("tema")
        if tema not in _TEMI_VALIDI:
            raise ValueError(
                f"La fonte '{nome}' ha tema '{tema}' non valido. "
                f"Ammessi: {sorted(_TEMI_VALIDI)}."
            )

        # Troncamento: intero positivo oppure None (nessun limite). Default 500.
        if "troncamento" not in fonte:
            fonte["troncamento"] = _DEFAULT_TRONCAMENTO
        tr = fonte["troncamento"]
        if tr is not None and (not isinstance(tr, int) or tr <= 0):
            raise ValueError(
                f"La fonte '{nome}' ha 'troncamento' non valido: {tr!r} "
                "(atteso intero positivo o null)."
            )

        # max: intero positivo oppure None (nessun limite di lettura).
        mx = fonte.get("max")
        if mx is not None and (not isinstance(mx, int) or mx <= 0):
            raise ValueError(
                f"La fonte '{nome}' ha 'max' non valido: {mx!r} "
                "(atteso intero positivo o null)."
            )

        fonte.setdefault("filtro_rilevanza", False)

        # I percorsi di fonti locali (file, non http) sono relativi alla cartella
        # del config: cosi' la demo/i test funzionano da qualunque working dir.
        if url and not url.startswith(("http://", "https://")):
            fonte["url"] = str((base / url).resolve())

    cfg.setdefault("out_dir", "out")
    cfg.setdefault("db_path", "data/seen.sqlite3")
    cfg.setdefault("finestra_dedup_settimane", 6)
    cfg.setdefault("soglia_overlap_dedup", 0.7)
    return cfg
