# Research Digest Agent — DRA

Beat: **Infrastruttura & Hardware AI** (chip NVIDIA/AMD/silicio custom, data
center, consumo energetico, colli di bottiglia della supply chain, cloud provider
e capacità di calcolo).

Ogni settimana l'agente monitora 12 fonti RSS/Atom pubbliche e produce un
**digest strutturato** su 5 sotto-temi fissi, consegnato via **email di notifica**
+ **sito web interno**. Target: CTO, investitori infrastrutturali, chi vuole
capire i vincoli reali dietro le promesse dei modelli.

La pipeline è **~80% codice deterministico / ~20% modello**: fetch, dedup,
classificazione, note interne e assemblaggio sono script; il modello LLM (Groq)
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
                    (LLM Groq: solo sintesi)          email (notifica/    sito HTML statico
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
backend/
├── src/
│   ├── schemas.py          schema dati (5 sezioni fisse, enum, note_interne)   [Fase 1]
│   ├── config.py           caricamento/validazione config                     [Fase 2]
│   ├── state.py            memoria persistente (SQLite): dedup + conteggi run
│   ├── pipeline.py         orchestrazione del run completo                    [Fase 6]
│   ├── raccolta/           acquisizione e selezione dei candidati
│   │   ├── fetch.py        raccolta RSS/Atom, stati fetch, troncamento         [Fase 2]
│   │   ├── dedup.py        anti-duplicati esatto + fuzzy + segnali             [Fase 4]
│   │   └── classify.py     classificazione tema + filtro rilevanza            [Fase 3]
│   ├── modello/            sintesi tramite modello (solo ~20% del lavoro)
│   │   ├── prompts.py      criteri editoriali + prompt di sintesi             [Fase 6]
│   │   ├── llm.py          adattatore LLM Groq (solo sintesi)                 [Fase 6]
│   │   └── sintesi.py      sintesi articoli + assemblaggio Digest             [Fase 6]
│   └── consegna/            output verso i canali reali
│       ├── deliver.py      consegna Markdown di anteprima                     [Fase 6]
│       ├── sito.py         backend del sito: genera data.json + copia il front [Fase 8]
│       ├── notifica.py     email settimanale (notifica/reminder) + note IT    [Fase 7]
│       └── note_interne.py note interne (fetch_failed / energia a zero)       [Fase 5]
├── main.py              entrypoint (LLM Groq)
├── config.yaml          beat, 12 fonti, dedup, sito, email  (produzione)
├── Dockerfile           immagine del backend/generatore
├── requirements.txt
├── data/                stato persistente: dedup (sqlite) + archivio digest (gitignored)
└── tests/               test deterministici (offline, LLM mockato)

frontend/concept/     interfaccia web (legge data.json e genera le pagine)
docker-compose.yml    backend (generator) + frontend (nginx)
claude-progress.txt   log di avanzamento per sessione (non versionato)
```

## Come funziona (pipeline)

1. **Fetch** (`raccolta/fetch.py`): legge i 12 feed, *fail-soft* (una fonte KO non
   blocca le altre). Distingue `fetch_ok` da `fetch_failed`. Tronca gli estratti a
   500 caratteri su confine di parola, tranne arXiv / Google Cloud Blog / Google
   Cloud Infrastructure (nessun limite).
2. **Deduplicazione** (`raccolta/dedup.py`): hash esatto (titolo+URL) su tutto lo
   storico, poi confronto *fuzzy* nella finestra di 4–6 settimane. Se l'overlap di
   parole/entità (Jaccard) supera la soglia (0,7) si valutano 3 segnali di novità
   (numerico, temporale, entità): almeno uno → aggiornamento legittimo; nessuno →
   duplicato scartato.
3. **Classificazione** (`raccolta/classify.py`): ogni articolo a esattamente 1 dei 5 temi o
   a `null` (revisione manuale). Filtro di rilevanza a monte per Google Cloud Blog
   (scarta database/sicurezza/off-beat prima della sintesi).
4. **Note interne** (`consegna/note_interne.py`): contatori di run consecutivi; `fetch_failed`
   ×3 o energia a 0 ×3 → nota per l'IT. Mai un blocco automatico.
5. **Sintesi** (`modello/sintesi.py` + `modello/llm.py`): per ogni articolo il modello scrive
   `sintesi` e `perche_conta` in italiano seguendo i criteri editoriali
   (`modello/prompts.py`); i metadati (titolo, fonte, link, data) restano quelli reali
   (grounding). arXiv → formula "I risultati preliminari di uno studio indicano
   che…" + nota preprint aggiunta dal codice.
6. **Assemblaggio** (`sintesi.assembla_digest`): costruisce il `Digest` con le 5
   sezioni; le sezioni vuote non invocano il modello.
7. **Consegna** (`consegna/notifica.py`, `consegna/sito.py`): email + dati del sito.
   Il backend scrive `sito/data.json` (archivio pubblico aggregato per tema) e
   copia `frontend/concept/index.html` in `sito/index.html`. Il frontend statico
   legge `data.json` e genera lato client homepage, cronologie e pagine articolo.

## Schema dati (sintesi)

```
Digest      = { data_generazione, sezioni:[5 fissi], note_interne:[…] }
Sezione     = { tema:enum[chip,data_center,energia,supply_chain,cloud_capacity],
                stato:enum[con_aggiornamenti,nessun_aggiornamento], articoli:[…] }
Articolo    = { titolo, fonti:[{nome,link}], data, sintesi, perche_conta, note? }
```
`perche_conta` è sempre obbligatorio; `note_interne` non è mai reso nel pubblico.

## Configurazione

Tutto in `config.yaml`:

- `fonti`: elenco con `nome`, `url`, `tema`, `max`, `troncamento` (int o `null`),
  `filtro_rilevanza` (solo Google Cloud Blog).
- `soglia_overlap_dedup` (0.7) e `finestra_dedup_settimane` (6) — calibrabili.
- `sito`: `homepage_url` (URL pubblico del sito — è il link che l'email di notifica
  manda ai lettori; **da sostituire** con il proprio), `out_dir`, `archivio_dir`,
  `badge_giorni` (soglia badge), `template` (default `frontend/concept/index.html`).
- `email`: **i destinatari non stanno in `config.yaml`** (sono dati personali e cambiano
  a ogni adozione del repo): si leggono da due variabili d'ambiente, indirizzi separati
  da virgola. `DIGEST_RECIPIENTS` (lettori del digest) è **obbligatoria** — senza, il run
  si ferma subito con un errore esplicito, prima di consumare chiamate al modello.
  `INTERNAL_NOTES_RECIPIENTS` (comparto IT) serve **solo** nei run che producono note
  interne. Restano due liste separate apposta: le note interne non devono mai
  raggiungere i lettori del digest (sez. 16.7/17.2).
  L'**invio** avviene via SMTP (Gmail) se sono presenti le variabili d'ambiente
  `SMTP_USER`/`SMTP_PASS` (vedi `.env.example`); altrimenti le email vengono solo
  stampate a log. Con Gmail `SMTP_PASS` è una **App Password** a 16 cifre (richiede
  la verifica in due passaggi), non la password dell'account.

---

## Avvio — in locale

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r backend/requirements.txt

cd backend
python -m pytest -q                # test offline, modello LLM e SMTP mockati

cp ../.env.example ../.env         # inserisci GROQ_API_KEY e DIGEST_RECIPIENTS
python main.py --config config.yaml
```

Il run scrive `out/digest.md`, genera `sito/data.json` + `sito/index.html` e invia
l'email via SMTP se `SMTP_USER`/`SMTP_PASS` sono impostate, altrimenti la stampa sul
terminale. Il sito usa `fetch('data.json')`, quindi **va servito via http** (aprire
`index.html` da `file://` non carica i dati):

```bash
python -m http.server -d sito 8080   # poi apri http://localhost:8080
```

> **Nota Python 3.14**: se `pydantic` non importa (`_pydantic_core` mancante),
> reinstallalo con `pip install --force-reinstall --no-cache-dir pydantic`
> (un wheel cp311 in cache non è compatibile). Con Docker il problema non si pone
> (l'immagine usa Python 3.12).

I test **mockano sempre** le chiamate al modello: non serve una API key per la
suite automatica, solo per un run reale.

---

## Avvio — con Docker (consigliato per testarlo)

Lo stack ha due servizi: `generator` (backend Python, gira una volta e termina) e
`web` (nginx, serve il sito quando il generatore ha finito).

```bash
export GROQ_API_KEY=...              # (PowerShell: $env:GROQ_API_KEY="...")
export DIGEST_RECIPIENTS=tu@example.com   # obbligatoria (in locale basta il tuo indirizzo)
docker compose up --build            # genera il sito e lo serve
# poi apri:  http://localhost:8080
```

- `generator` esegue `main.py --config config.yaml` (richiede `GROQ_API_KEY` e
  `DIGEST_RECIPIENTS`) e scrive `data.json` + `index.html` nel volume `sito`.
  Le variabili si possono mettere anche in un file `.env` in root, che
  `docker compose` legge da solo (vedi `.env.example`).
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

> Se stai configurando il repo per la prima volta nel tuo account, parti da
> **[Adottare il repo](#adottare-il-repo)**: qui sotto c'è solo come funziona il
> workflow, là c'è la procedura passo-passo.

1. I secret stanno in *Settings → Secrets and variables → Actions*: `GROQ_API_KEY`
   e `DIGEST_RECIPIENTS` sono obbligatori (elenco completo in
   *[Adottare il repo](#adottare-il-repo)*).
2. Il job genera digest + `sito/` (`data.json` + `index.html`), lo allega come
   artifact e **ricommitta** lo stato (`backend/data/seen.sqlite3`,
   `backend/data/archivio/`) e `sito/` nel repo, così il dedup ricorda gli
   articoli già pubblicati.
3. **Pubblicazione.** Il workflow non conosce l'host: si limita a ricommittare
   `sito/`. Pubblicare vuol dire collegare al repo un hosting statico qualsiasi che
   serva quella cartella e ridispieghi a ogni push, poi impostare
   `sito.homepage_url` in `config.yaml` con l'URL ottenuto. Scelta dell'host e
   caveat in *[Adottare il repo](#adottare-il-repo)*.

## Interfaccia web (frontend/concept)

L'interfaccia web è **una sola**, definitiva, in `frontend/concept/index.html`,
separata dal backend Python (`backend/src/`, `backend/main.py`). È una web-app statica vanilla
(HTML/CSS/JS, zero dipendenze esterne) che **legge `data.json`** (prodotto dal
backend) e genera lato client: home → cronologia tema → articolo con "Perché conta"
e nota preprint. In home compaiono solo i temi con aggiornamenti della settimana,
box **autocentrati**, badge "Nuovo" (≤ `badge_giorni`) e finestra settimana
(≤ `settimana_giorni`) calcolati lato client dalle date assolute in `data.json`.

Stile "KVAdra": tema quasi-nero, accento rosa/rosso, card glass, **sfondo ripreso da
kakashi.ventures** (gli 8 simboli reali del sito, incorporati e disposti sparsi su
canvas, che si accendono di rosso vicino al cursore), homepage compatta in una sola
schermata, logo placeholder KVA.

Per vederla con i dati reali serve `data.json` accanto a `index.html`: generarlo con
`python main.py` e servire `sito/` (vedi *Avvio — in locale*), oppure via Docker:

```bash
docker compose up concept          # shell del concept senza dati → http://localhost:8082
docker compose up web              # sito generato con i dati → http://localhost:8080
```

---

## Stato

Tutte le 8 fasi sono implementate (`claude-progress.txt` per il dettaglio); la
suite conta **92 test verdi**. Prima del deploy reale restano (non-bloccanti):

- verifica dei feed dall'ambiente di produzione (possibili anti-bot da IP cloud);
- verifica manuale con una `GROQ_API_KEY` reale e con SMTP Gmail reale;
- calibrazione della soglia di dedup (0.7) e dell'elenco entità note sul flusso reale.

## Test

```bash
cd backend
python -m pytest -q
```

Ogni fase è coperta da test basati sugli scenari Given/When/Then del documento di
progettazione (sez. 16–18). Un commit avviene solo a test verdi.
