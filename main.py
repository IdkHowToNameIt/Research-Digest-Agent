"""Entrypoint del Research Digest Agent — DRA.

Due modalità:
  python main.py            -> con modello (Gemini): richiede GEMINI_API_KEY
  python main.py --demo     -> demo offline (sintesi deterministica, nessuna key)

La pipeline è ~80% script (fetch, dedup, classificazione, note interne,
assemblaggio); il modello interviene solo sulla sintesi testuale degli articoli.
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from src.config import load_config
from src.consegna.notifica import invia_tutti, prepara_invii, spedisci_console
from src.pipeline import costruisci_digest
from src.consegna.sito import carica_archivio, genera_sito, salva_digest_pubblico
from src.consegna.deliver import deliver_markdown

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Digest Agent — DRA")
    parser.add_argument("--demo", action="store_true", help="Modalità offline senza modello")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.demo:
        genera = None
    else:
        from src.modello.gemini import GeminiNonConfigurato, crea_generatore
        try:
            genera = crea_generatore(model=cfg.get("model"))
        except GeminiNonConfigurato as exc:
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
    )
    print(f"Sito aggiornato: {len(file_sito)} pagine in {sito_cfg.get('out_dir', 'sito')}/")

    # Email settimanale (sempre una) + eventuale email di note interne (sez. 17).
    invii = prepara_invii(digest, cfg)
    invia_tutti(invii, spedisci_console)
    if digest.note_interne:
        print(f"[note interne] {len(digest.note_interne)} segnalazione/i per il team.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
