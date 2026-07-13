"""Generazione dei dati del sito web interno (sez. 18).

Separazione netta backend/frontend: il backend NON genera più HTML. Produce un
unico file `data.json` (contratto dati) che il frontend statico
(`frontend/concept/index.html`) legge via fetch e con cui genera da solo, lato
client, le pagine richieste: homepage (box solo per i temi con aggiornamenti nella
settimana), cronologia per tema e pagina del singolo articolo.

`genera_sito`:
- scrive `<out_dir>/data.json` = archivio storico aggregato per tema + soglie;
- copia tutti i file del frontend (index.html + stile.css + app.js + sfondo.js)
  in `<out_dir>/`, così `<out_dir>/` è la publish-dir pronta per un hosting
  statico (es. Render Static Site).

Il badge "nuovo aggiornamento" (soglia configurabile, default 2 giorni) e la vista
"questa settimana" (7 giorni) sono calcolati LATO CLIENT dal frontend a partire
dalle date assolute presenti nei dati: qui non marchiamo nulla staticamente.

`note_interne` non entra MAI nei dati del sito (16.7): `data.json` è costruito solo
dall'archivio pubblico (contenuto_pubblico(), che le esclude) e dalla data del
digest corrente, mai dalle note interne.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..schemas import TEMI_ORDINE, Digest, Stato, Tema

ETICHETTE = {
    Tema.chip: "Chip",
    Tema.data_center: "Data center",
    Tema.energia: "Energia",
    Tema.supply_chain: "Supply chain",
    Tema.cloud_capacity: "Cloud capacity",
}

BADGE_GIORNI_DEFAULT = 2
SETTIMANA_GIORNI_DEFAULT = 7
# Template del frontend copiato accanto a data.json come index.html della publish-dir.
TEMPLATE_DEFAULT = "frontend/concept/index.html"


def temi_con_aggiornamenti(digest: Digest) -> list[Tema]:
    """Temi con stato con_aggiornamenti nel digest corrente (informativo)."""
    return [s.tema for s in digest.sezioni if s.stato is Stato.con_aggiornamenti and s.articoli]


def raccogli_per_tema(archivio: list[dict]) -> dict[Tema, list[dict]]:
    """Aggrega gli articoli pubblici dell'archivio per tema, più recenti prima.

    `archivio` = lista di digest pubblici (dict, es. Digest.contenuto_pubblico()),
    ciascuno con `data_generazione`. Ogni articolo eredita quel timestamp (`_ts`)
    quando manca una data propria.
    """
    per_tema: dict[Tema, list[dict]] = {t: [] for t in Tema}
    for pub in sorted(archivio, key=lambda d: d.get("data_generazione", ""), reverse=True):
        ts = pub.get("data_generazione", "")
        for sez in pub.get("sezioni", []):
            try:
                tema = Tema(sez.get("tema"))
            except ValueError:
                continue
            for art in sez.get("articoli", []):
                item = dict(art)
                item["_ts"] = ts
                per_tema[tema].append(item)
    return per_tema


def costruisci_dati(
    digest_corrente: Digest,
    archivio: list[dict],
    badge_giorni: int = BADGE_GIORNI_DEFAULT,
    settimana_giorni: int = SETTIMANA_GIORNI_DEFAULT,
) -> dict:
    """Costruisce il contratto dati (`data.json`) consumato dal frontend.

    Forma:
        {
          "generato": "YYYY-MM-DD",
          "badge_giorni": 2,
          "settimana_giorni": 7,
          "temi": [ {"id","nome","articoli":[
              {"titolo","fonti":[{nome,link}],"data","sintesi","perche_conta","note"} ]}, ... ]
        }
    I 5 temi sono sempre presenti e in ordine canonico (anche senza articoli).
    """
    per_tema = raccogli_per_tema(archivio)
    temi = []
    for tema in TEMI_ORDINE:
        articoli = [
            {
                "titolo": a.get("titolo", ""),
                "fonti": a.get("fonti", []),
                "data": a.get("data") or a.get("_ts", ""),
                "sintesi": a.get("sintesi", ""),
                "perche_conta": a.get("perche_conta", ""),
                "note": a.get("note"),
            }
            for a in per_tema.get(tema, [])
        ]
        temi.append({"id": tema.value, "nome": ETICHETTE[tema], "articoli": articoli})
    return {
        "generato": digest_corrente.data_generazione,
        "badge_giorni": badge_giorni,
        "settimana_giorni": settimana_giorni,
        "temi": temi,
    }


def genera_sito(
    digest_corrente: Digest,
    archivio: list[dict],
    out_dir: str,
    badge_giorni: int = BADGE_GIORNI_DEFAULT,
    template_path: str = TEMPLATE_DEFAULT,
) -> list[str]:
    """Scrive data.json e copia il template frontend in index.html.

    Ritorna i percorsi scritti. La cartella `out_dir` diventa la publish-dir del
    sito statico (index.html + data.json).
    """
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    scritti: list[str] = []

    dati = costruisci_dati(digest_corrente, archivio, badge_giorni)
    percorso_dati = base / "data.json"
    percorso_dati.write_text(
        json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    scritti.append(str(percorso_dati))

    tpl = Path(template_path)
    if tpl.exists():
        # Il frontend è suddiviso in più file (index.html + stile.css + app.js +
        # sfondo.js): copia l'intera cartella del template accanto a data.json, così
        # la publish-dir è completa. `template_path` indica index.html; i fogli di
        # stile e gli script sono i suoi file fratelli.
        for asset in sorted(tpl.parent.iterdir()):
            if asset.is_file():
                destinazione = base / asset.name
                shutil.copyfile(asset, destinazione)
                scritti.append(str(destinazione))

    return scritti


def carica_archivio(dir_archivio: str) -> list[dict]:
    """Carica tutti i digest pubblici (JSON) salvati in `dir_archivio`."""
    p = Path(dir_archivio)
    if not p.exists():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(p.glob("*.json"))]


def salva_digest_pubblico(digest: Digest, dir_archivio: str) -> str:
    """Salva il contenuto pubblico del digest (senza note_interne) come JSON."""
    p = Path(dir_archivio)
    p.mkdir(parents=True, exist_ok=True)
    nome = f"{digest.data_generazione}.json"
    percorso = p / nome
    percorso.write_text(
        json.dumps(digest.contenuto_pubblico(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(percorso)
