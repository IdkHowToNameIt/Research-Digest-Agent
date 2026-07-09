"""Consegna tecnica del digest in Markdown (nuovo schema a 5 sezioni).

Canale di produzione reale = email + sito (Fasi 7-8). Questo modulo resta utile
per debug/anteprima. Non renderizza MAI `note_interne` (solo pubblico, sez. 16.7).
"""
from __future__ import annotations

from pathlib import Path

from ..schemas import (
    MESSAGGIO_NESSUN_AGGIORNAMENTO,
    Digest,
    Sezione,
    Stato,
)

_ETICHETTE = {
    "chip": "Chip",
    "data_center": "Data center",
    "energia": "Energia",
    "supply_chain": "Supply chain",
    "cloud_capacity": "Cloud capacity",
}


def _sezione_md(sez: Sezione) -> list[str]:
    righe = [f"## {_ETICHETTE.get(sez.tema.value, sez.tema.value)}", ""]
    if sez.stato is Stato.nessun_aggiornamento or not sez.articoli:
        righe += [f"_{MESSAGGIO_NESSUN_AGGIORNAMENTO}_", ""]
        return righe
    for a in sez.articoli:
        fonti = ", ".join(f"[{f.nome}]({f.link})" for f in a.fonti)
        righe += [f"### {a.titolo}", ""]
        righe.append(f"- **Fonti:** {fonti}")
        righe.append(f"- **Data:** {a.data or 'n/d'}")
        if a.note:
            righe.append(f"- **Nota:** {a.note}")
        righe += ["", a.sintesi, "", f"**Perché conta:** {a.perche_conta}", ""]
    return righe


def rendi_markdown(digest: Digest) -> str:
    """Rende il digest come stringa Markdown."""
    righe = ["# Research Digest — Infrastruttura & Hardware AI", "",
             f"_Generato il {digest.data_generazione}_", ""]
    for sez in digest.sezioni:
        righe += _sezione_md(sez)
    return "\n".join(righe).rstrip() + "\n"


def deliver_markdown(digest: Digest, out_dir: str = "out") -> str:
    """Scrive il digest come file Markdown e ne restituisce il percorso."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / "digest.md"
    path.write_text(rendi_markdown(digest), encoding="utf-8")
    return str(path)
