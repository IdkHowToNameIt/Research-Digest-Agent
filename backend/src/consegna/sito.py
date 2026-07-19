"""Generazione dei dati del sito web interno (sez. 18).

Separazione netta backend/frontend: il backend NON genera HTML. Produce dei file
JSON (contratto dati) che il frontend statico (`frontend/concept/index.html`)
legge via fetch e con cui genera da solo, lato client, le pagine: homepage (un box
per tema con aggiornamenti nella settimana), lista dei gruppi-giorno di un tema
(ognuno col titolo riassuntivo) e dettaglio del gruppo con le notizie di quel
giorno. Le notizie di uno stesso tema nello stesso giorno confluiscono in un
unico gruppo.

**Dati suddivisi per scalare (evita di scaricare tutta la storia a ogni visita):**
- `data.json` = **indice leggero**: soglie + per ogni tema id/nome, il file di
  lista e i gruppi *recenti* (ultimi giorni) per la landing. Unico file all'avvio.
- `tema-<id>.json` = **lista leggera** del tema: metadati dei gruppi (data, titolo,
  n. articoli, anteprima di alcuni titoli), SENZA corpi. Caricata aprendo il tema;
  basta a lista e filtri per data.
- `tema-<id>-<anno>.json` = **corpi** degli articoli del tema per quell'anno,
  caricati **on-demand** aprendo un giorno di quell'anno. Così un tema con anni di
  storia non si scarica mai tutto in una volta, senza perdere alcun dato.

`genera_sito`:
- scrive `<out_dir>/data.json` (indice) + un `<out_dir>/tema-<id>.json` per tema;
- copia i file del frontend (index.html + stile.css + app.js + sfondo.js) in
  `<out_dir>/`, aggiungendo a `index.html` un token `?v=<generato>` sui riferimenti
  a JS/CSS (**cache-busting**): dopo un deploy il browser non serve versioni vecchie.

Il badge "nuovo aggiornamento" (soglia configurabile, default 2 giorni) e la vista
"questa settimana" (7 giorni) sono calcolati LATO CLIENT dal frontend a partire
dalle date assolute presenti nei dati: qui non marchiamo nulla staticamente.

`note_interne` non entra MAI nei dati del sito (16.7): tutto è costruito solo
dall'archivio pubblico (contenuto_pubblico(), che le esclude) e dalla data del
digest corrente, mai dalle note interne.
"""
from __future__ import annotations

import json
import math
import shutil
from datetime import date
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
# Finestra (giorni) dei gruppi inclusi nell'indice per la landing "questa settimana".
# Più larga della settimana (7) per dare margine: il frontend re-filtra a 7 giorni
# rispetto a OGGI, quindi qualche giorno di scorta copre le visite dopo il run.
RECENTI_GIORNI_DEFAULT = 14
# Lista leggera di un tema (metadati dei gruppi, senza corpi): caricata aprendo il tema.
NOME_FILE_TEMA = "tema-{id}.json"
# Corpi degli articoli di un tema, in bucket annuali: caricati aprendo un giorno di quell'anno.
NOME_FILE_TEMA_ANNO = "tema-{id}-{anno}.json"
# Quanti titoli d'anteprima mettere nella lista leggera (per la card del gruppo).
ANTEPRIMA_TITOLI = 3
# Velocità di lettura per la stima del tempo di lettura mostrato all'utente
# (~200 parole/minuto, lettura silenziosa media). Il valore è indicativo.
PAROLE_AL_MINUTO = 200
# Asset del frontend a cui aggiungere il token ?v=<generato> in index.html (cache-busting).
# pdf.js è versionato; jspdf.umd.min.js è una libreria vendorizzata stabile (non versionata).
ASSET_VERSIONABILI = ("app.js", "stile.css", "sfondo.js", "pdf.js")
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


def _articolo_pubblico(a: dict, ts: str) -> dict:
    """Proietta un articolo d'archivio nel formato del sito (data con fallback al ts)."""
    return {
        "titolo": a.get("titolo", ""),
        "fonti": a.get("fonti", []),
        "data": a.get("data") or ts,
        "sintesi": a.get("sintesi", ""),
        "perche_conta": a.get("perche_conta", ""),
        "note": a.get("note"),
    }


def raccogli_gruppi_per_tema(archivio: list[dict]) -> dict[Tema, dict[str, dict]]:
    """Aggrega l'archivio in gruppi (tema -> data -> {titolo, articoli}).

    Le notizie di uno stesso tema nello stesso giorno confluiscono in un unico
    gruppo. Il `titolo` del gruppo è quello riassuntivo salvato nel digest
    (`Sezione.gruppi`, generato dal modello); se assente (archivi vecchi) resta
    None e verrà rimpiazzato da un fallback a valle. Gli archivi sono scorsi dal
    più recente, così un eventuale titolo/articolo dello stesso (tema,data) su più
    run mantiene la versione più recente in testa.
    """
    per_tema: dict[Tema, dict[str, dict]] = {t: {} for t in Tema}
    for pub in sorted(archivio, key=lambda d: d.get("data_generazione", ""), reverse=True):
        ts = pub.get("data_generazione", "")
        for sez in pub.get("sezioni", []):
            try:
                tema = Tema(sez.get("tema"))
            except ValueError:
                continue
            titoli = {g.get("data"): g.get("titolo") for g in sez.get("gruppi", [])}
            for art in sez.get("articoli", []):
                item = _articolo_pubblico(art, ts)
                data = item["data"]
                gruppo = per_tema[tema].setdefault(data, {"titolo": None, "articoli": []})
                gruppo["articoli"].append(item)
                if gruppo["titolo"] is None and titoli.get(data):
                    gruppo["titolo"] = titoli[data]
    return per_tema


def _minuti_lettura(articoli: list[dict]) -> int:
    """Tempo di lettura stimato (minuti) di un gruppo, dai testi delle sue voci.

    Conta le parole dei campi che il lettore legge davvero (titolo, sintesi,
    perché conta, nota) su tutte le voci del gruppo e divide per PAROLE_AL_MINUTO,
    arrotondando per eccesso. Minimo 1 minuto se c'è del testo; 0 se il gruppo è
    vuoto (caso difensivo: un gruppo pubblicato ha sempre almeno una voce).
    """
    parole = 0
    for a in articoli:
        for campo in ("titolo", "sintesi", "perche_conta", "note"):
            testo = a.get(campo) or ""
            parole += len(testo.split())
    if parole <= 0:
        return 0
    return max(1, math.ceil(parole / PAROLE_AL_MINUTO))


def costruisci_dati(
    digest_corrente: Digest,
    archivio: list[dict],
    badge_giorni: int = BADGE_GIORNI_DEFAULT,
    settimana_giorni: int = SETTIMANA_GIORNI_DEFAULT,
) -> dict:
    """Costruisce il contratto dati (`data.json`) consumato dal frontend.

    Forma:
        {
          "generato": "YYYY-MM-DD", "badge_giorni": 2, "settimana_giorni": 7,
          "temi": [ {"id","nome","gruppi":[
              {"data","titolo","articoli":[
                 {"titolo","fonti":[{nome,link}],"data","sintesi","perche_conta","note"} ]} ]}, ... ]
        }
    Le notizie di uno stesso tema nello stesso giorno sono un unico gruppo, con un
    titolo riassuntivo. I 5 temi sono sempre presenti e in ordine canonico; i gruppi
    sono ordinati dal giorno più recente. Titolo del gruppo mancante (archivi vecchi)
    -> fallback sul titolo del primo articolo.
    """
    per_tema = raccogli_gruppi_per_tema(archivio)
    temi = []
    for tema in TEMI_ORDINE:
        gruppi = []
        for data in sorted(per_tema[tema].keys(), reverse=True):  # più recente prima
            g = per_tema[tema][data]
            articoli = g["articoli"]
            titolo = g["titolo"] or (articoli[0]["titolo"] if articoli else "")
            gruppi.append({"data": data, "titolo": titolo, "articoli": articoli,
                           "minuti_lettura": _minuti_lettura(articoli)})
        temi.append({"id": tema.value, "nome": ETICHETTE[tema], "gruppi": gruppi})
    return {
        "generato": digest_corrente.data_generazione,
        "badge_giorni": badge_giorni,
        "settimana_giorni": settimana_giorni,
        "temi": temi,
    }


def _giorni_tra(a: str, b: str) -> int:
    """Giorni interi tra due date ISO (a - b). Tollerante a valori sporchi/vuoti."""
    try:
        return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days
    except (ValueError, TypeError):
        return 10**9


def _indice_da_full(full: dict, recenti_giorni: int, invio_email_url: str = "") -> dict:
    """Deriva l'indice leggero (`data.json`) dai dati completi.

    Per ogni tema tiene solo i gruppi entro `recenti_giorni` da `generato`
    (per la landing), con il minimo indispensabile: data, titolo, n. articoli.
    Il dettaglio completo vive nei file `tema-<id>.json`.

    `invio_email_url` (opzionale) è l'endpoint del Worker per l'invio del PDF via
    email: finisce in `data.json` solo se valorizzato, così il frontend accende il
    bottone "Invia via email" solo quando il relay è configurato (feature-flag).
    """
    generato = full["generato"]
    temi = []
    for t in full["temi"]:
        recenti = [
            {"data": g["data"], "titolo": g["titolo"], "n_articoli": len(g["articoli"]),
             "minuti_lettura": g.get("minuti_lettura", 0)}
            for g in t["gruppi"]
            if _giorni_tra(generato, g["data"]) <= recenti_giorni
        ]
        temi.append({
            "id": t["id"],
            "nome": t["nome"],
            "file": NOME_FILE_TEMA.format(id=t["id"]),
            "recenti": recenti,
        })
    indice = {
        "generato": generato,
        "badge_giorni": full["badge_giorni"],
        "settimana_giorni": full["settimana_giorni"],
        "temi": temi,
    }
    if invio_email_url:
        indice["invio_email_url"] = invio_email_url
    return indice


def costruisci_indice(
    digest_corrente: Digest,
    archivio: list[dict],
    badge_giorni: int = BADGE_GIORNI_DEFAULT,
    settimana_giorni: int = SETTIMANA_GIORNI_DEFAULT,
    recenti_giorni: int = RECENTI_GIORNI_DEFAULT,
) -> dict:
    """Indice leggero del sito (`data.json`): soglie + per tema i soli gruppi recenti."""
    full = costruisci_dati(digest_corrente, archivio, badge_giorni, settimana_giorni)
    return _indice_da_full(full, recenti_giorni)


def _lista_leggera_tema(t: dict) -> dict:
    """Lista leggera di un tema (`tema-<id>.json`): metadati dei gruppi, SENZA corpi.

    Basta a render la vista lista (data, titolo, n. articoli, anteprima di alcuni
    titoli) e ai filtri per data. I corpi degli articoli stanno nei bucket annuali.
    """
    gruppi = [
        {
            "data": g["data"],
            "titolo": g["titolo"],
            "n_articoli": len(g["articoli"]),
            "minuti_lettura": g.get("minuti_lettura", 0),
            "anteprima_titoli": [a.get("titolo", "") for a in g["articoli"][:ANTEPRIMA_TITOLI]],
        }
        for g in t["gruppi"]
    ]
    return {"id": t["id"], "nome": t["nome"], "gruppi": gruppi}


def _bucket_anni_tema(t: dict) -> dict[str, dict]:
    """Corpi degli articoli di un tema raggruppati per anno (`tema-<id>-<anno>.json`).

    Ritorna {anno -> {"anno", "gruppi": [{data, titolo, articoli}]}}. Il frontend,
    aprendo un giorno, ricava l'anno dalla data e carica solo quel bucket.
    """
    buckets: dict[str, dict] = {}
    for g in t["gruppi"]:
        anno = (g["data"] or "")[:4] or "0000"
        b = buckets.setdefault(anno, {"anno": anno, "gruppi": []})
        b["gruppi"].append(
            {"data": g["data"], "titolo": g["titolo"], "articoli": g["articoli"]}
        )
    return buckets


def _cache_bust(html: str, token: str) -> str:
    """Aggiunge `?v=<token>` ai riferimenti JS/CSS in index.html (cache-busting).

    Cerca gli asset tra virgolette singole o doppie (es. `src="app.js"`), così il
    browser scarica la nuova versione dopo un deploy invece di servire la cache.
    """
    if not token:
        return html
    for asset in ASSET_VERSIONABILI:
        html = html.replace(f'"{asset}"', f'"{asset}?v={token}"')
        html = html.replace(f"'{asset}'", f"'{asset}?v={token}'")
    return html


def _svuota_dir(base: Path) -> None:
    """Rimuove tutto il contenuto di `base` (file e sottocartelle), non la cartella.

    La publish-dir è interamente rigenerata a ogni run: svuotarla prima di scrivere
    evita che file orfani di run/architetture precedenti (es. vecchie pagine HTML)
    sopravvivano e finiscano deployati. La cartella stessa viene preservata (può
    essere un mount/volume, es. in docker-compose).
    """
    for elem in base.iterdir():
        if elem.is_dir() and not elem.is_symlink():
            shutil.rmtree(elem)
        else:
            elem.unlink()


def genera_sito(
    digest_corrente: Digest,
    archivio: list[dict],
    out_dir: str,
    badge_giorni: int = BADGE_GIORNI_DEFAULT,
    template_path: str = TEMPLATE_DEFAULT,
    settimana_giorni: int = SETTIMANA_GIORNI_DEFAULT,
    recenti_giorni: int = RECENTI_GIORNI_DEFAULT,
    invio_email_url: str = "",
) -> list[str]:
    """Scrive indice + lista/bucket per-tema e copia il frontend nella publish-dir.

    Ritorna i percorsi scritti. La cartella `out_dir` diventa la publish-dir del
    sito statico:
    - `data.json` = indice leggero (l'unico caricato all'avvio);
    - `tema-<id>.json` = lista leggera del tema (metadati dei gruppi, senza corpi),
      caricata aprendo il tema;
    - `tema-<id>-<anno>.json` = corpi degli articoli del tema per quell'anno,
      caricati aprendo un giorno di quell'anno (così un tema con anni di storia non
      si scarica mai tutto in una volta, senza perdere alcun dato);
    - index.html/stile.css/app.js/sfondo.js, con `?v=<generato>` sui riferimenti
      JS/CSS di index.html (cache-busting).
    La publish-dir viene svuotata prima della scrittura, così riflette l'ultimo run.
    """
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    _svuota_dir(base)
    scritti: list[str] = []

    full = costruisci_dati(digest_corrente, archivio, badge_giorni, settimana_giorni)
    generato = full["generato"]

    # Indice leggero (data.json): l'unico file caricato all'avvio dal frontend.
    percorso_indice = base / "data.json"
    percorso_indice.write_text(
        json.dumps(
            _indice_da_full(full, recenti_giorni, invio_email_url),
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    scritti.append(str(percorso_indice))

    for t in full["temi"]:
        # Lista leggera del tema (tema-<id>.json): metadati, caricata aprendo il tema.
        percorso_lista = base / NOME_FILE_TEMA.format(id=t["id"])
        percorso_lista.write_text(
            json.dumps(_lista_leggera_tema(t), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        scritti.append(str(percorso_lista))
        # Corpi in bucket annuali (tema-<id>-<anno>.json): caricati aprendo un giorno.
        for anno, bucket in sorted(_bucket_anni_tema(t).items()):
            percorso_bucket = base / NOME_FILE_TEMA_ANNO.format(id=t["id"], anno=anno)
            percorso_bucket.write_text(
                json.dumps(bucket, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            scritti.append(str(percorso_bucket))

    tpl = Path(template_path)
    if tpl.exists():
        # Il frontend è suddiviso in più file (index.html + stile.css + app.js +
        # sfondo.js): copia l'intera cartella del template nella publish-dir.
        # `template_path` indica index.html; a esso si applica il cache-busting.
        for asset in sorted(tpl.parent.iterdir()):
            if asset.is_file():
                destinazione = base / asset.name
                if asset.name == "index.html":
                    testo = _cache_bust(asset.read_text(encoding="utf-8"), generato)
                    destinazione.write_text(testo, encoding="utf-8")
                else:
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
