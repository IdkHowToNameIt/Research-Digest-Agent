"""Entrypoint del Research Digest Agent — DRA.

  python main.py [--config config.yaml]   -> richiede GROQ_API_KEY, DIGEST_RECIPIENTS

La pipeline è ~80% script (fetch, dedup, classificazione, note interne,
assemblaggio); il modello LLM (Groq) interviene solo sulla sintesi testuale degli
articoli.

Di default fa tutto in un colpo (`--fase tutto`). Le due fasi si possono separare
per pubblicare il sito subito e mandare le email più tardi:

  python main.py --fase genera                      # digest + sito, nessuna email
  python main.py --fase email --attendi-invio 06:30 # attende e poi manda

Serve perché l'email rimanda al sito: pubblicare prima e scrivere dopo evita di
mandare un link a una pagina non ancora aggiornata. Tra le due fasi il digest
passa da un file di lavoro (`out_dir/digest-run.json`), che contiene anche le note
interne — quindi NON è l'archivio pubblico e non va servito (sez. 16.7).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.config import load_config
from src.consegna.notifica import (
    ENV_DESTINATARI_DIGEST,
    DestinatariNonConfigurati,
    HomepageNonConfigurata,
    attendi_fino_a,
    crea_sender,
    invia_tutti,
    leggi_destinatari,
    leggi_homepage_url,
    prepara_invii,
)
from src.pipeline import costruisci_digest
from src.consegna.sito import carica_archivio, genera_sito, salva_digest_pubblico
from src.consegna.deliver import deliver_markdown
from src.metriche import (
    RaccoltaMetriche,
    carica_metriche,
    salva_metriche,
    scrivi_dashboard,
)
from src.schemas import Digest

load_dotenv()

NOME_FILE_CONSEGNA = "digest-run.json"


def _path_consegna(cfg: dict) -> Path:
    return Path(cfg.get("out_dir", "out")) / NOME_FILE_CONSEGNA


def fase_genera(cfg: dict) -> Digest:
    """Digest + archivio + sito + metriche operative. Nessuna email."""
    from src.modello.llm import LLMNonConfigurato, crea_generatore

    # Le metriche del run: l'uso di token arriva dal generatore (callback), i dati
    # operativi dalla pipeline. L'orario del run è l'identità del record.
    raccolta = RaccoltaMetriche()
    ora_run = datetime.now(timezone.utc)
    try:
        genera = crea_generatore(
            model=cfg.get("model"),
            modelli_fallback=cfg.get("modelli_fallback"),
            on_uso=raccolta.registra_uso,
        )
    except LLMNonConfigurato as exc:
        print(f"[errore] {exc}", file=sys.stderr)
        sys.exit(2)

    digest = costruisci_digest(cfg, genera, metriche=raccolta)
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

    # Metriche operative del run (osservabilità): un JSON per run, come l'archivio.
    metriche_dir = cfg.get("metriche_dir", "data/metriche")
    record = raccolta.finalizza(
        cfg.get("prezzi", {}),
        digest.data_generazione,
        ora_run.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        float(cfg.get("tasso_cambio_usd_eur", 1.0)),
    )
    percorso_metriche = salva_metriche(record, metriche_dir)
    print(f"Metriche run salvate: {record.costo.prompt_tokens}+{record.costo.completion_tokens} "
          f"token, costo stimato {record.costo.costo_stimato} € -> {percorso_metriche}")

    # Dati per la dashboard: dopo genera_sito (che svuota la publish-dir) e dopo aver
    # salvato il record di questo run, così metriche.json include l'intero storico.
    percorso_dash = scrivi_dashboard(carica_metriche(metriche_dir), sito_cfg.get("out_dir", "sito"))
    print(f"Dashboard metriche aggiornata -> {percorso_dash}")
    return digest


def fase_email(cfg: dict, digest: Digest, attendi_invio: str | None = None) -> None:
    """Email settimanale (sempre una) + eventuale email di note interne (sez. 17).
    Sender scelto in automatico: SMTP reale se configurato, altrimenti console."""
    attendi_fino_a(attendi_invio)
    invii = prepara_invii(digest, cfg)
    invia_tutti(invii, crea_sender())
    if digest.note_interne:
        print(f"[note interne] {len(digest.note_interne)} segnalazione/i per il team.",
              file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Digest Agent — DRA")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--fase", choices=("tutto", "genera", "email"), default="tutto",
        help="tutto (default) = genera e invia; genera = digest+sito senza email; "
             "email = invia il digest lasciato da --fase genera",
    )
    parser.add_argument(
        "--attendi-invio", metavar="HH:MM", default=None,
        help="Attende fino a questo orario UTC prima di inviare le email "
             "(solo con --fase email/tutto). Oltre 90 minuti di attesa non aspetta.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    # Controllo anticipato: destinatari e homepage servono solo in fondo, ma
    # scoprirli mancanti dopo la pipeline sprecherebbe un run intero di chiamate
    # al modello — e con le fasi separate se ne accorgerebbe solo all'ora di invio.
    try:
        leggi_destinatari(ENV_DESTINATARI_DIGEST)
        leggi_homepage_url(cfg)
    except (DestinatariNonConfigurati, HomepageNonConfigurata) as exc:
        print(f"[errore] {exc}", file=sys.stderr)
        sys.exit(2)

    consegna = _path_consegna(cfg)

    if args.fase == "email":
        if not consegna.exists():
            print(f"[errore] manca {consegna}: eseguire prima `--fase genera`.",
                  file=sys.stderr)
            sys.exit(2)
        digest = Digest.model_validate_json(consegna.read_text(encoding="utf-8"))
        fase_email(cfg, digest, args.attendi_invio)
        return

    digest = fase_genera(cfg)

    if args.fase == "genera":
        # Il digest passa alla fase email via file: contiene le note interne, quindi
        # resta in out/ (gitignored) e non finisce mai nei dati del sito (sez. 16.7).
        consegna.parent.mkdir(parents=True, exist_ok=True)
        consegna.write_text(digest.model_dump_json(indent=2), encoding="utf-8")
        print(f"Email rimandate alla fase successiva: digest in {consegna}")
        return

    fase_email(cfg, digest, args.attendi_invio)


if __name__ == "__main__":
    main()
