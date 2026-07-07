"""Consegna del digest: scrive un file Markdown leggibile.

Sostituibile con altri canali (email, Slack, un documento) come deliverable
opzionale.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..schemas import Digest


def deliver_markdown(digest: Digest, out_dir: str = "out") -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    safe_beat = "".join(ch if ch.isalnum() else "-" for ch in digest.beat.lower())
    safe_beat = re.sub(r"-{2,}", "-", safe_beat).strip("-") or "digest"
    path = Path(out_dir) / f"digest-{safe_beat}.md"

    righe = [f"# Research Digest — {digest.beat}", "", f"_Generato il {digest.generato_il}_", ""]
    if not digest.voci:
        righe.append("Nessuna novità nuova in questa esecuzione.")
    for i, v in enumerate(digest.voci, 1):
        righe += [
            f"## {i}. {v.titolo}",
            "",
            f"- **Fonte:** {v.fonte}",
            f"- **Link:** {v.url}",
            f"- **Data:** {v.data or 'n/d'}",
            f"- **Tag:** {', '.join(v.tag) if v.tag else 'n/d'}",
            "",
            v.sintesi,
            "",
            f"**Perché conta:** {v.perche_conta}",
            "",
        ]
    path.write_text("\n".join(righe), encoding="utf-8")
    return str(path)
