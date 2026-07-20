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
- copia la build del frontend (frontend/dist: index.html + assets/) in `<out_dir>/`.
  Il cache-busting degli asset non si fa piu' a mano: Vite mette l'hash del
  contenuto nei nomi dei file, quindi un asset cambiato cambia nome da solo. I JSON
  dei dati, che il nome lo mantengono, restano versionati lato client con
  `?v=<generato>`.

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
import sys
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
# Build del frontend (React + Vite) copiata accanto ai JSON nella publish-dir.
# Va prodotta PRIMA di questo passo con `npm run build` in frontend/ (in CI c'è uno
# step apposta): se manca, il sito viene pubblicato senza interfaccia.
# NB: relativo a backend/, la cartella da cui gira main.py (come il percorso che
# main.py passa davvero). Scriverlo senza "../" lo rendeva un default morto.
TEMPLATE_DEFAULT = "../frontend/dist/index.html"


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
    - la build del frontend (index.html + assets/), copiata ricorsivamente.
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
        # Il frontend e' una build Vite (frontend/dist): index.html piu' una
        # sottocartella assets/ con JS e CSS. Si copia l'intero albero nella
        # publish-dir, RICORSIVAMENTE: la versione precedente copiava solo i file
        # diretti (`asset.is_file()`) perche' il frontend era piatto, e con la
        # build avrebbe pubblicato l'index senza il suo bundle — pagina bianca,
        # senza alcun errore che lo segnalasse.
        scritti.extend(_copia_albero(tpl.parent, base))

    return scritti


def _copia_albero(sorgente: Path, destinazione: Path) -> list[str]:
    """Copia ricorsivamente `sorgente` dentro `destinazione`. Ritorna i file scritti.

    Niente cache-busting a mano: Vite mette gia' l'hash del contenuto nei nomi dei
    file generati, quindi un asset cambiato cambia nome da solo. I JSON dei dati,
    che il nome invece non lo cambiano, restano versionati lato client dal
    parametro `?v=<generato>` (conVersione in src/dati.js).
    """
    scritti: list[str] = []
    for elemento in sorted(sorgente.rglob("*")):
        if not elemento.is_file():
            continue
        relativo = elemento.relative_to(sorgente)
        arrivo = destinazione / relativo
        arrivo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(elemento, arrivo)
        scritti.append(str(arrivo))
    return scritti


def carica_archivio(dir_archivio: str) -> list[dict]:
    """Carica tutti i digest pubblici (JSON) salvati in `dir_archivio`."""
    p = Path(dir_archivio)
    if not p.exists():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(p.glob("*.json"))]


def _link_articolo(a: dict) -> set[str]:
    """Identita' di un articolo: i link delle sue fonti (il titolo come ripiego).

    L'identita' NON e' il titolo: la sintesi e il titolo sono riscritti dal
    modello a ogni run, quindi lo stesso articolo tornerebbe con un testo diverso
    e verrebbe archiviato due volte. I link invece sono stabili. Si usa un
    insieme perche' un articolo puo' avere piu' fonti (Google News multi-testata):
    basta un link in comune perche' sia lo stesso articolo.
    """
    link = {(f.get("link") or "").strip().lower()
            for f in (a.get("fonti") or []) if (f.get("link") or "").strip()}
    return link or {(a.get("titolo") or "").strip().lower()}


def _fondi_sezioni(esistenti: list[dict], nuove: list[dict]) -> list[dict]:
    """Unisce le sezioni di due digest della stessa data, senza perdere articoli.

    Gli articoli gia' archiviati vincono sui nuovi a parita' di chiave: sono il
    testo che il lettore ha gia' visto (email inviata, PDF scaricati), riscriverlo
    con una sintesi diversa lo renderebbe incoerente. Si aggiungono in coda solo
    le voci davvero nuove. Lo `stato` viene ricalcolato: una sezione che si
    riempie non puo' restare 'nessun_aggiornamento' (lo schema lo rifiuterebbe).
    """
    per_tema = {s.get("tema"): s for s in esistenti}
    fuse: list[dict] = []
    for nuova in nuove:
        vecchia = per_tema.get(nuova.get("tema"))
        if vecchia is None:
            fuse.append(nuova)
            continue
        articoli = list(vecchia.get("articoli") or [])
        viste: set[str] = set()
        for a in articoli:
            viste |= _link_articolo(a)
        for a in nuova.get("articoli") or []:
            link = _link_articolo(a)
            if link & viste:      # gia' archiviato: vince la versione pubblicata
                continue
            articoli.append(a)
            viste |= link
        gruppi = list(vecchia.get("gruppi") or [])
        date_viste = {g.get("data") for g in gruppi}
        for g in nuova.get("gruppi") or []:
            if g.get("data") not in date_viste:
                gruppi.append(g)
                date_viste.add(g.get("data"))
        fusa = dict(nuova)
        fusa["articoli"] = articoli
        fusa["gruppi"] = gruppi
        fusa["stato"] = "con_aggiornamenti" if articoli else "nessun_aggiornamento"
        fuse.append(fusa)
    return fuse


def salva_digest_pubblico(digest: Digest, dir_archivio: str) -> str:
    """Salva il contenuto pubblico del digest (senza note_interne) come JSON.

    NON distruttivo: se esiste gia' un archivio per la stessa data, i due digest
    vengono FUSI invece che sovrascritti. Serve perche' il nome del file e' la
    data di generazione, quindi due run nello stesso giorno scrivono lo stesso
    file — e il secondo run e' quasi sempre vuoto, perche' il dedup ha gia'
    marcato come visti gli articoli del primo. Il 2026-07-20 questo ha ridotto un
    digest da 158 articoli a 1, svuotando il sito pubblicato (DECISIONI sez. 15).
    """
    p = Path(dir_archivio)
    p.mkdir(parents=True, exist_ok=True)
    nome = f"{digest.data_generazione}.json"
    percorso = p / nome
    contenuto = digest.contenuto_pubblico()

    if percorso.exists():
        try:
            precedente = json.loads(percorso.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Archivio illeggibile: si riparte da quello nuovo, ma lo si dice.
            print(f"[attenzione] archivio {percorso} illeggibile ({exc}): "
                  f"viene sostituito invece che fuso", file=sys.stderr)
        else:
            contenuto["sezioni"] = _fondi_sezioni(
                precedente.get("sezioni") or [], contenuto.get("sezioni") or []
            )

    percorso.write_text(
        json.dumps(contenuto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(percorso)
