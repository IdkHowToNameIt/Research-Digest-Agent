# Research Digest Agent — DRA

Beat: **Infrastruttura & Hardware AI** (chip NVIDIA/AMD/silicio custom, data
center, consumo energetico, colli di bottiglia della supply chain, cloud provider
e capacità di calcolo).

Ogni settimana l'agente monitora 12 fonti RSS/Atom pubbliche e produce un
**digest strutturato** su 5 sotto-temi fissi, consegnato via **email di notifica**
+ **sito web interno**. Target: CTO, investitori infrastrutturali, chi vuole
capire i vincoli reali dietro le promesse dei modelli.

La pipeline è **~80% codice deterministico / ~20% modello**: fetch, dedup,
classificazione, note interne e assemblaggio sono script; il modello (Gemini)
interviene **solo** sulla sintesi testuale dei singoli articoli e non sceglie mai
le fonti né inventa URL.

---

## Cosa produce ogni run

1. **Un'email settimanale** (sempre una, mai zero):
   - *notifica* con link alla homepage, se almeno una sezione ha aggiornamenti;
   - *reminder* ("Nessun aggiornamento questa settimana - DRA") se tutte vuote.
2. **Il sito web interno** (statico): homepage con box per i temi aggiornati nella
   settimana, una pagina di cronologia per tema e una pagina per articolo.
3. **Eventuale email di note interne** al comparto IT (fetch falliti ripetuti o
   sezione energia a zero per 3 run) — solo segnalazione, mai un blocco.
4. Un Markdown tecnico di anteprima in `out/digest.md`.

## Principi vincolanti

- **Mai contenuto inventato o forzato.** Sezione senza materiale → nota di stato
  esplicita (`nessun_aggiornamento`), mai riempita artificialmente.
- **Dati quantitativi** (capex, energia) riportati solo se citati testualmente
  dalla fonte, mai riformulati/arrotondati dal modello.
- **`note_interne`** generato solo da script, **mai** esposto nel sito o nell'email
  ai lettori.

---

## Architettura

Il digest è modellato come **5 sezioni fisse** (una per sotto-tema), sempre
presenti anche se vuote, ciascuna con uno `stato` esplicito
(`con_aggiornamenti` / `nessun_aggiornamento`).

```
                 ┌─────────────────────  BACKEND (Python, batch) ──────────────────────┐
  12 feed RSS ──▶│ fetch ─▶ dedup ─▶ classificazione ─▶ note interne ─▶ sintesi ─▶ Digest │
                 └───────┬───────────────────────────────────┬──────────────┬──────────┘
                         │                                    │              │
                    (Gemini: solo sintesi)             email (notifica/    sito HTML statico
                                                        reminder + note IT)   (in un volume)
                                                                                   │
                 ┌─────────────────────  FRONTEND (nginx statico) ─────────────────┴──┐
                 │        serve index.html / tema-*.html / articolo-*.html            │
                 └────────────────────────────────────────────────────────────────────┘
```

### Perché frontend e backend separati così (e non un backend web dinamico)

Il sito è **statico per progetto** (sez. 18 del documento di progettazione):
nessun login, nessuno stato lato server, e il badge "nuovo aggiornamento" è
calcolato **lato client** in JavaScript. Di conseguenza:

- **Backend** = il generatore Python (`main.py`), un *batch settimanale* che
  produce i file HTML e invia l'email. Non resta in ascolto.
- **Frontend** = **nginx** che serve i file statici generati, da un volume condiviso.

Un backend web dinamico (Flask/FastAPI) sarebbe **sovra-ingegnerizzazione** e
contraddirebbe la scelta di tenere il sito interno semplice e senza stato: non
c'è nulla da calcolare a runtime per ogni richiesta. La separazione utile è
quindi *generazione* (Python) vs *servizio dei file* (nginx), come nel
`docker-compose.yml`.

---

## Struttura del progetto

```
src/
├── schemas.py        schema dati (5 sezioni fisse, enum, note_interne)   [Fase 1]
├── config.py         caricamento/validazione config                     [Fase 2]
├── classify.py       classificazione tema + filtro rilevanza            [Fase 3]
├── note_interne.py   note interne (fetch_failed / energia a zero)       [Fase 5]
├── prompts.py        criteri editoriali + prompt di sintesi             [Fase 6]
├── gemini.py         adattatore modello (solo sintesi)                  [Fase 6]
├── sintesi.py        sintesi articoli + assemblaggio Digest             [Fase 6]
├── pipeline.py       orchestrazione del run completo                    [Fase 6]
├── notifica.py       email settimanale (notifica/reminder) + note IT    [Fase 7]
├── sito.py           generatore sito interno (homepage/tema/articolo)   [Fase 8]
├── state.py          memoria persistente (SQLite): dedup + conteggi run
└── tools/
    ├── fetch.py      raccolta RSS/Atom, stati fetch, troncamento         [Fase 2]
    ├── dedup.py      anti-duplicati esatto + fuzzy + segnali            [Fase 4]
    └── deliver.py    consegna Markdown di anteprima                     [Fase 6]

main.py               entrypoint (--demo / Gemini reale)
config.yaml           beat, 12 fonti, dedup, sito, email  (produzione)
config.demo.yaml      config offline con feed locali        (demo/Docker)
Dockerfile            immagine del backend/generatore
docker-compose.yml    backend (generator) + frontend (nginx)
tests/                test deterministici (offline, Gemini mockato)
claude-progress.txt   log di avanzamento per sessione
```

## Come funziona (pipeline)

1. **Fetch** (`tools/fetch.py`): legge i 12 feed, *fail-soft* (una fonte KO non
   blocca le altre). Distingue `fetch_ok` da `fetch_failed`. Tronca gli estratti a
   500 caratteri su confine di parola, tranne arXiv / Google Cloud Blog / Google
   Cloud Infrastructure (nessun limite).
2. **Deduplicazione** (`tools/dedup.py`): hash esatto (titolo+URL) su tutto lo
   storico, poi confronto *fuzzy* nella finestra di 4–6 settimane. Se l'overlap di
   parole/entità (Jaccard) supera la soglia (0,7) si valutano 3 segnali di novità
   (numerico, temporale, entità): almeno uno → aggiornamento legittimo; nessuno →
   duplicato scartato.
3. **Classificazione** (`classify.py`): ogni articolo a esattamente 1 dei 5 temi o
   a `null` (revisione manuale). Filtro di rilevanza a monte per Google Cloud Blog
   (scarta database/sicurezza/off-beat prima della sintesi).
4. **Note interne** (`note_interne.py`): contatori di run consecutivi; `fetch_failed`
   ×3 o energia a 0 ×3 → nota per l'IT. Mai un blocco automatico.
5. **Sintesi** (`sintesi.py` + `gemini.py`): per ogni articolo il modello scrive
   `sintesi` e `perche_conta` in italiano seguendo i criteri editoriali
   (`prompts.py`); i metadati (titolo, fonte, link, data) restano quelli reali
   (grounding). arXiv → formula "I risultati preliminari di uno studio indicano
   che…" + nota preprint aggiunta dal codice.
6. **Assemblaggio** (`sintesi.assembla_digest`): costruisce il `Digest` con le 5
   sezioni; le sezioni vuote non invocano il modello.
7. **Consegna** (`notifica.py`, `sito.py`): email + sito statico.

## Schema dati (sintesi)

```
Digest      = { data_generazione, sezioni:[5 fissi], note_interne:[…] }
Sezione     = { tema:enum[chip,data_center,energia,supply_chain,cloud_capacity],
                stato:enum[con_aggiornamenti,nessun_aggiornamento], articoli:[…] }
Articolo    = { titolo, fonti:[{nome,link}], data, sintesi, perche_conta, note? }
```
`perche_conta` è sempre obbligatorio; `note_interne` non è mai reso nel pubblico.

## Configurazione

Tutto in `config.yaml` (produzione) o `config.demo.yaml` (offline):

- `fonti`: elenco con `nome`, `url`, `tema`, `max`, `troncamento` (int o `null`),
  `filtro_rilevanza` (solo Google Cloud Blog).
- `soglia_overlap_dedup` (0.7) e `finestra_dedup_settimane` (6) — calibrabili.
- `sito`: `homepage_url`, `out_dir`, `archivio_dir`, `badge_giorni` (soglia badge).
- `email`: `destinatari_digest`, `destinatari_note_interne` (liste nel repo).

---

## Avvio — in locale

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

python -m pytest -q                # 88 test, offline, nessuna API key
python main.py --demo --config config.demo.yaml   # run offline completo
```

Il run demo scrive `out/digest.md`, genera il sito in `sito/` e stampa l'email
sul terminale. Apri `sito/index.html` nel browser per vedere il risultato.

> **Nota Python 3.14**: se `pydantic` non importa (`_pydantic_core` mancante),
> reinstallalo con `pip install --force-reinstall --no-cache-dir pydantic`
> (un wheel cp311 in cache non è compatibile). Con Docker il problema non si pone
> (l'immagine usa Python 3.12).

### Modalità reale (Gemini)

```bash
cp .env.example .env              # inserisci GEMINI_API_KEY
python main.py --config config.yaml
```

I test **mockano sempre** le chiamate al modello: non serve una API key per la
suite automatica, solo per una verifica manuale.

---

## Avvio — con Docker (consigliato per testarlo)

Lo stack ha due servizi: `generator` (backend Python, gira una volta e termina) e
`web` (nginx, serve il sito quando il generatore ha finito).

```bash
docker compose up --build          # genera il sito e lo serve
# poi apri:  http://localhost:8080
```

- `generator` esegue di default `main.py --demo --config config.demo.yaml`
  (offline, nessuna API key) e scrive i file nel volume `sito`.
- `web` (nginx) pubblica quei file su **http://localhost:8080**.

Per rigenerare dopo una modifica: `docker compose up --build --force-recreate`.

Per fermare / ripulire:

```bash
docker compose down                # ferma i container
docker compose down -v             # rimuove anche i volumi (sito + storico)
```

## Avvio — automatico settimanale (GitHub Actions)

Il workflow `.github/workflows/digest-settimanale.yml` esegue la pipeline reale
ogni lunedì alle 06:00 UTC (e a mano da *Actions → Run workflow*):

1. Su GitHub aggiungi il secret `GEMINI_API_KEY`
   (*Settings → Secrets and variables → Actions*).
2. Il job genera digest + sito, allega il sito come artifact e **ricommitta** lo
   stato (`data/seen.sqlite3`, `data/archivio/`) e `sito/` nel repo, così il dedup
   ricorda gli articoli già pubblicati tra un run e l'altro.
3. Pubblicazione sulla rete interna: il server interno fa `git pull` e serve
   `sito/`, oppure un passo aggiuntivo copia `sito/` via scp/rsync (vedi commenti
   nel workflow). L'invio email reale (SMTP) è ancora da configurare (sez. 17.4).

## Bozza visiva (design)

`design/bozza-homepage.html` è una **bozza visiva statica autonoma** (apribile
direttamente nel browser) per discutere colori/logo/tipografia/animazioni —
non è l'implementazione finale del sito (`src/sito.py`).

### Modalità reale (Gemini) con Docker

```bash
export GEMINI_API_KEY=...          # (Windows PowerShell: $env:GEMINI_API_KEY="...")
docker compose run --rm generator python main.py --config config.yaml
docker compose up web              # servi il sito generato
```

---

## Stato

Tutte le 8 fasi sono implementate (`claude-progress.txt` per il dettaglio); la
suite conta **88 test verdi**. Prima del deploy reale restano (non-bloccanti):

- verifica dei feed dall'ambiente di produzione (possibili anti-bot da IP cloud);
- provider **SMTP reale** al posto della stampa su console (sez. 17.4);
- **stile visivo** del sito — colori/logo (sez. 18, volutamente rimandato);
- verifica manuale con una `GEMINI_API_KEY` reale;
- calibrazione della soglia di dedup (0.7) e dell'elenco entità note sul flusso reale.

## Test

```bash
python -m pytest -q
```

Ogni fase è coperta da test basati sugli scenari Given/When/Then del documento di
progettazione (sez. 16–18). Un commit avviene solo a test verdi.
