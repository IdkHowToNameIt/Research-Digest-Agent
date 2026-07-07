"""Entrypoint del Research Digest Agent.

Due modalità:
  python main.py            -> modalità AGENTE (usa l'LLM; richiede OPENAI_API_KEY)
  python main.py --demo     -> modalità DEMO offline (nessuna chiave, regole semplici)

La modalità demo serve a mostrare subito la pipeline (raccolta -> dedup ->
sintesi -> output strutturato -> consegna) anche senza chiavi API. La modalità
agente è quella "vera": è il modello a selezionare e sintetizzare.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.config import load_config
from src.schemas import Digest, DigestItem
from src.state import SeenStore
from src.tools.fetch import fetch_candidates
from src.tools.dedup import filtra_nuove
from src.tools.deliver import deliver_markdown

# Legge OPENAI_API_KEY (e altre variabili) dal file .env nella cartella corrente.
load_dotenv()


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_demo(cfg: dict) -> tuple[Digest, str]:
    """Pipeline senza LLM: utile per la demo e per i test.

    Usa uno stato in memoria: la demo riparte pulita a ogni esecuzione e
    mostra di nuovo tutte le voci (è pensata per essere ripetibile).
    """
    store = SeenStore(":memory:")
    candidati = fetch_candidates(cfg)
    nuove = filtra_nuove(candidati, store)[: cfg.get("max_voci", 5)]

    voci = [
        DigestItem(
            titolo=c.titolo,
            fonte=c.fonte,
            url=c.url,
            data=c.data,
            sintesi=(c.estratto[:240] or c.titolo),
            perche_conta="(demo) selezionata automaticamente per il beat",
            tag=[cfg.get("beat_slug", "beat")],
        )
        for c in nuove
    ]
    digest = Digest(beat=cfg["beat"], generato_il=_ora(), voci=voci)
    for v in voci:
        store.mark_seen(v.url, cfg["beat"])
    path = deliver_markdown(digest, cfg.get("out_dir", "out"))
    store.close()
    return digest, path


async def run_agent(cfg: dict) -> tuple[Digest, str]:
    """Pipeline con l'LLM (Agents SDK)."""
    from agents import Runner
    from src.agent import build_agent

    agent, store = build_agent(cfg)
    result = await Runner.run(
        agent,
        f"Genera il digest della settimana per il beat '{cfg['beat']}'.",
        max_turns=cfg.get("max_turns", 4),  # limita le iterazioni: contiene costi e tempi
    )
    digest: Digest = result.final_output
    digest.generato_il = _ora()  # il momento della generazione lo conosce il programma

    # Grounding: tieni solo le voci con un URL realmente tra le fonti raccolte.
    url_candidati = {c.url for c in fetch_candidates(cfg)}
    valide = [v for v in digest.voci if str(v.url) in url_candidati]
    if len(valide) != len(digest.voci):
        print(f"[grounding] scartate {len(digest.voci) - len(valide)} voci "
              f"con URL non tra le fonti raccolte", file=sys.stderr)
    digest.voci = valide

    # Vincoli "morbidi" applicati a runtime (vedi schemas.py): al massimo 3 tag.
    for v in digest.voci:
        v.tag = v.tag[:3]

    for v in digest.voci:
        store.mark_seen(str(v.url), cfg["beat"])
    path = deliver_markdown(digest, cfg.get("out_dir", "out"))
    store.close()
    return digest, path


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Digest Agent (KVA starter)")
    parser.add_argument("--demo", action="store_true", help="Modalità offline senza LLM")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.demo:
        digest, path = run_demo(cfg)
    else:
        digest, path = asyncio.run(run_agent(cfg))

    print(f"Digest generato: {len(digest.voci)} voci -> {path}")


if __name__ == "__main__":
    main()
