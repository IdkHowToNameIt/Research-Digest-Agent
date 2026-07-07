"""Caricamento e validazione della configurazione del beat da config.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(path).resolve()
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Validazione minima, con messaggi chiari (gli studenti modificheranno il file).
    if not cfg.get("beat"):
        raise ValueError(f"In {config_path.name} manca il campo obbligatorio 'beat'.")
    if not cfg.get("fonti"):
        raise ValueError(f"In {config_path.name} serve almeno una fonte sotto 'fonti'.")

    # I percorsi delle fonti locali (file, non http) vanno risolti rispetto alla
    # cartella del config, non alla working directory: così funziona anche da
    # cron o lanciando lo script da un'altra cartella.
    base = config_path.parent
    for fonte in cfg.get("fonti", []):
        url = str(fonte.get("url", ""))
        if url and not url.startswith(("http://", "https://")):
            fonte["url"] = str((base / url).resolve())

    cfg.setdefault("out_dir", "out")
    cfg.setdefault("db_path", "data/seen.sqlite3")
    cfg.setdefault("max_voci", 5)
    cfg.setdefault("max_turns", 4)
    return cfg
