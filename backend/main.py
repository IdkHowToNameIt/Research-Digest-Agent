"""Entrypoint del Research Digest Agent — DRA.

  python main.py [--config config.yaml]   -> richiede GROQ_API_KEY, DIGEST_RECIPIENTS

La pipeline è ~80% script (fetch, dedup, classificazione, note interne,
assemblaggio); il modello LLM (Groq) interviene solo sulla sintesi testuale degli
articoli.
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from src.config import load_config
from src.consegna.notifica import (
    ENV_DESTINATARI_DIGEST,
    DestinatariNonConfigurati,
    crea_sender,
    invia_tutti,
    leggi_destinatari,
    prepara_invii,
)
from src.pipeline import costruisci_digest
from src.consegna.sito import carica_archivio, genera_sito, salva_digest_pubblico
from src.consegna.deliver import deliver_markdown

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Digest Agent — DRA")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)

    from src.modello.llm import LLMNonConfigurato, crea_generatore
    try:
        genera = crea_generatore(
            model=cfg.get("model"),
            modelli_fallback=cfg.get("modelli_fallback"),
        )
    except LLMNonConfigurato as exc:
        print(f"[errore] {exc}", file=sys.stderr)
        sys.exit(2)

    # Controllo anticipato: i destinatari servono solo in fondo, ma scoprirli
    # mancanti dopo la pipeline sprecherebbe un run intero di chiamate al modello.
    try:
        leggi_destinatari(ENV_DESTINATARI_DIGEST)
    except DestinatariNonConfigurati as exc:
        print(f"[errore] {exc}", file=sys.stderr)
        sys.exit(2)

    digest = costruisci_digest(cfg, genera)
    path = deliver_markdown(digest, cfg.get("out_dir", "out"))

    n_articoli = sum(len(s.articoli) for s in digest.sezioni)
    con_agg = [s.tema.value for s in digest.sezioni if s.articoli]
    print(f"Digest generato ({digest.data_generazione}): {n_articoli} articoli "
          f"in {len(con_agg)} sezioni con aggiornamenti {con_agg} -> {path}")

    # Sito web interno (sez. 18): archivia il digest pubblico e rigenera le pagine.
    sito_cfg = cfg.get("sito", {})
    archivio_dir = sito_cfg.get("archivio_dir", "data/archivio")
    salva_digest_pubblico(digest, archivio_dir)
    archivio = carica_archivio(archivio_dir)
    file_sito = genera_sito(
        digest, archivio, sito_cfg.get("out_dir", "sito"),
        badge_giorni=int(sito_cfg.get("badge_giorni", 2)),
        template_path=sito_cfg.get("template", "../frontend/concept/index.html"),
        settimana_giorni=int(sito_cfg.get("settimana_giorni", 7)),
    )
    print(f"Sito aggiornato: {len(file_sito)} file in {sito_cfg.get('out_dir', 'sito')}/ "
          f"(data.json indice + tema-<id>.json + frontend)")

    # Email settimanale (sempre una) + eventuale email di note interne (sez. 17).
    # Sender scelto in automatico: SMTP reale se configurato, altrimenti console.
    invii = prepara_invii(digest, cfg)
    invia_tutti(invii, crea_sender())
    if digest.note_interne:
        print(f"[note interne] {len(digest.note_interne)} segnalazione/i per il team.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
