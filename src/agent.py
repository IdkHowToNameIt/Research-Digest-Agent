"""Costruzione dell'agente: modello + istruzioni + strumenti + output strutturato.

Usa l'OpenAI Agents SDK (portabile, supporta anche altri provider via LiteLLM).
Il modello decide quando chiamare lo strumento `cerca_novita`; il codice degli
strumenti resta deterministico e affidabile.
"""
from __future__ import annotations

from agents import Agent, function_tool

from .prompts import ISTRUZIONI
from .schemas import Digest
from .state import SeenStore
from .tools.fetch import fetch_candidates
from .tools.dedup import filtra_nuove


def build_agent(cfg: dict) -> tuple[Agent, SeenStore]:
    store = SeenStore(cfg.get("db_path", "data/seen.sqlite3"))

    @function_tool
    def cerca_novita() -> list[dict]:
        """Cerca le novità dalle fonti del beat ed esclude ciò che è già stato
        riportato in passato. Restituisce solo voci nuove (titolo, url, fonte,
        data, estratto)."""
        candidati = fetch_candidates(cfg)
        nuove = filtra_nuove(candidati, store)
        return [c.to_dict() for c in nuove]

    agent = Agent(
        name=f"Research Digest Agent — {cfg['beat']}",
        instructions=ISTRUZIONI.format(beat=cfg["beat"], max_voci=cfg.get("max_voci", 5)),
        tools=[cerca_novita],
        model=cfg.get("model", "gpt-4.1-mini"),
        output_type=Digest,
    )
    return agent, store
