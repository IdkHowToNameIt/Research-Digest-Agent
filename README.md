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
   settimana, una pagina di cronologia per tema, una pagina per articolo e una
   **dashboard di osservabilità** (stato fonti, costi, deduplica, copertura temi).
3. **Eventuale email di note interne** al comparto IT (fetch falliti ripetuti o
   sezione energia a zero per 3 run) — solo segnalazione, mai un blocco.
4. Un Markdown tecnico di anteprima in `out/digest.md`.
5. **Le metriche operative del run** (`backend/data/metriche/<run>.json`), che
   alimentano la dashboard: token/costo, stato di ogni fonte, statistiche dedup,
   copertura dei temi.

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
│   ├── metriche.py         metriche operative per run + dati dashboard
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
├── data/                stato persistente: dedup (sqlite) + archivio digest + metriche (gitignored)
└── tests/               test deterministici (offline, LLM mockato)

frontend/              interfaccia web React + Vite
├── src/               componenti, livello dati, sfondo canvas, export PDF
├── package.json       dipendenze JS (+ package-lock.json, usato da `npm ci`)
└── dist/              build prodotta da `npm run build` (gitignored)
sito/                 output pubblicato dall'hosting statico (generato, committato dalla CI)
docker-compose.yml    backend (generator) + frontend (nginx)
.env.example          variabili d'ambiente da impostare (copia in .env)
```

## Come funziona (pipeline)

1. **Fetch** (`raccolta/fetch.py`): legge i 12 feed, *fail-soft* (una fonte KO non
   blocca le altre). Distingue `fetch_ok` da `fetch_failed`. Tronca gli estratti a
   500 caratteri su confine di parola, tranne arXiv / Google Cloud Blog / Google
   Cloud Infrastructure (nessun limite).
2. **Deduplicazione** (`raccolta/dedup.py`): per le fonti marcate `aggregatore:
   true` (oggi solo Google News) si tiene **una voce per storia** prima di tutto
   il resto, quindi anche prima delle chiamate al modello: N testate che
   riscrivono lo stesso fatto condividono azienda e cifra («TSMC» + «100
   miliardi») anche quando non condividono le parole, e il confronto fuzzy qui
   sotto non può vederle (è pensato per *una fonte per notizia*). Le voci
   accorpate diventano la nota «ripreso da N testate». Dettagli e misure in
   [`DECISIONI.md`](DECISIONI.md) §23.1 e §24.
   Poi, per tutte le fonti: hash esatto (titolo+URL) su tutto lo
   storico, poi confronto *fuzzy* nella finestra di 4–6 settimane. Se l'overlap di
   parole/entità (Jaccard) supera la soglia (0,7) si valutano 3 segnali di novità
   (numerico, temporale, entità): almeno uno → aggiornamento legittimo; nessuno →
   duplicato scartato.
3. **Classificazione** (`raccolta/classify.py`): ogni articolo a esattamente 1 dei 5 temi o
   a `null` (revisione manuale). Filtro di rilevanza a monte per le fonti
   generaliste — Google Cloud Blog e Tom's Hardware — che scarta l'off-beat
   (database, sicurezza, offerte, gadget) prima della sintesi. Il confronto con
   `PAROLE_BEAT` è per prefisso ancorato a inizio parola, così i plurali passano
   ma nessuna chiave scatta a metà parola (`mw` in "firmware").
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
   copia la build del frontend (`frontend/dist/`) nella publish-dir. L'app React
   legge `data.json` e genera lato client homepage, cronologie e pagine articolo.
8. **Metriche** (`metriche.py`): raccolte durante il run (stato fonti, esiti dedup,
   copertura e token/costo del modello) e salvate in `backend/data/metriche/<run>.json`
   (un file per run). Da tutti i record si scrive `sito/metriche.json`, che alimenta
   la dashboard di osservabilità. Lo storico parte dal primo run (nessun retro-fill).

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
  `filtro_rilevanza` (fonti generaliste: Google Cloud Blog, Tom's Hardware),
  `finestra_giorni` e `aggregatore` (vedi sotto).
- `soglia_overlap_dedup` (0.7) e `finestra_dedup_settimane` (6) — calibrabili.
- `finestra_articoli_giorni` (14): scarta in raccolta le voci pubblicate da più di
  N giorni, **prima** del dedup e delle chiamate al modello. Il dedup risponde a
  "l'ho già pubblicato?", non a "è ancora attuale?" — senza questo filtro il primo
  run dopo un azzeramento dello stato pesca tutto il backlog dei feed. Le voci
  senza data leggibile vengono tenute (fail-open). Assente o `null` = nessun filtro.
- `finestra_giorni` **per singola fonte**: sovrascrive la finestra globale solo per
  quella fonte. Serve a chi pubblica di rado: `Google Cloud — Infrastructure` esce a
  raffiche distanti (il 2026-07-21 l'ultimo post aveva 35 giorni) e con i 14 giorni
  globali non entrava **mai**, lasciando il tema `data_center` a un blog generalista.
  Oggi quelle due fonti a bassa frequenza stanno a 45. **Non alzare invece la
  finestra globale**: le fonti quotidiane (Google News, Tom's Hardware, NVIDIA)
  riverserebbero notizie vecchie nel settimanale. Prima di applicarlo a una fonte,
  guardane la frequenza reale: Meta Engineering *sembrava* un caso simile ma
  pubblica ogni ~4 giorni, e il suo problema è la pertinenza, non la data.
  Motivazioni e misure in [`DECISIONI.md`](DECISIONI.md) §23.3.
- `sito`: `homepage_url` (URL pubblico del sito — è il link che l'email di notifica
  manda ai lettori. Nel repo è un placeholder: impostalo con la variabile d'ambiente
  **`HOMEPAGE_URL`**, che ha la precedenza su questo campo, oppure sostituiscilo qui.
  Se resta il placeholder il run si ferma con un errore), `out_dir`, `archivio_dir`,
  `badge_giorni` (soglia badge), `template` (default `../frontend/dist/index.html`).
- `metriche_dir` (default `data/metriche`), `prezzi` e `tasso_cambio_usd_eur`: `prezzi`
  è il listino Groq in **USD/1M token** per modello (input/output); `tasso_cambio_usd_eur`
  converte in **euro** il costo mostrato in dashboard. Sul free tier il costo reale è 0,
  ma i token si contano comunque e la dashboard stima quanto costerebbe sull'API a pagamento.
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

## Adottare il repo

Questa sezione è per chi **prende il repo e lo fa girare nel proprio account**, da
zero. Se invece devi lavorare sul codice, salta a *[Avvio — in locale](#avvio--in-locale)*.

A regime il sistema gira da solo: una GitHub Action settimanale esegue la pipeline,
ricommitta i risultati nel repo, e l'hosting statico ripubblica il sito a ogni push.
Non c'è nessun server da gestire e nessun servizio nostro nel mezzo.

### a) Prendi il repo

**Fork** (*Fork* in alto a destra) se vuoi restare agganciato all'originale per
ricevere aggiornamenti; **clone + push su un repo nuovo** se preferisci una copia
indipendente:

```bash
git clone <url-di-questo-repo> dra && cd dra
git remote set-url origin <url-del-tuo-repo-vuoto>
git push -u origin main
```

Il repo ti arriva con lo storico dei digest già generati da noi (`sito/`,
`backend/data/archivio/`). Per ripartire da zero, svuota `backend/data/archivio/` e
`backend/data/metriche/`, cancella `backend/data/seen.sqlite3` e `sito/`: la prima
run li ricrea (la dashboard riparte da vuota). Se li tieni,
il dedup non ti riproporrà gli articoli già usciti.

### b) Crea i secret

*Settings → Secrets and variables → Actions → New repository secret*. **Nessun
secret è nel repo** e nessuno ha un default silenzioso: se manca un obbligatorio, il
run si ferma subito con un errore che dice quale.

| Secret | Obbligatorio | Dove si prende |
|---|---|---|
| `GROQ_API_KEY` | **Sì** | Gratis su [console.groq.com/keys](https://console.groq.com/keys) (free tier ampio, basta un account) |
| `DIGEST_RECIPIENTS` | **Sì** | Lo decidi tu: gli indirizzi dei lettori del digest, separati da virgola |
| `INTERNAL_NOTES_RECIPIENTS` | Solo per le note interne | Gli indirizzi di chi gestisce il sistema. Serve **solo** nei run che producono note operative; se manca, quel run fallisce |
| `SMTP_USER` / `SMTP_PASS` | No | Per inviare le email davvero. Con Gmail `SMTP_PASS` è una **App Password** a 16 cifre (*Account Google → Sicurezza → Verifica in due passaggi → Password per le app*), **non** la password dell'account. Senza questi due, le email vengono solo stampate nel log del run |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | No | Default Gmail: `smtp.gmail.com`, `587`, mittente = `SMTP_USER` |

`DIGEST_RECIPIENTS` e `INTERNAL_NOTES_RECIPIENTS` sono **due liste distinte apposta**:
le note interne segnalano guasti e anomalie e non devono finire ai lettori del digest.

Serve poi una **variabile**, non un secret. Stessa pagina, **scheda *Variables*** →
*New repository variable*:

| Variabile | Obbligatoria | Valore |
|---|---|---|
| `HOMEPAGE_URL` | **Sì** | L'URL pubblico del tuo sito: è il link che l'email settimanale manda ai lettori. Lo ottieni al punto (d), quindi puoi tornarci dopo |

Sta tra le *Variables* e non tra i *Secrets* perché un URL pubblico non è un segreto
(i secret sono mascherati nei log, e mascherare l'indirizzo del sito renderebbe
solo più difficile leggere i run). In alternativa puoi sostituire `sito.homepage_url`
in `backend/config.yaml`, ma `HOMEPAGE_URL` vince sul file e ti evita di modificare
il repo. Se non imposti né l'una né l'altro, nel config resta il placeholder
`https://DA-SOSTITUIRE.example.com` e **il run si ferma con un errore**: meglio di un
digest che invita a leggere il sito su un indirizzo finto.

### c) Abilita la Action settimanale

**Su un fork le Action sono disabilitate di default.** Vai su *Actions* e conferma
(*"I understand my workflows, go ahead and enable them"*). Se hai fatto clone + push
su un repo tuo, sono già attive.

Due cose che sorprendono spesso:

- **GitHub disattiva gli scheduled workflow dopo 60 giorni di inattività** del repo
  (e sui fork il `schedule` può non partire affatto). Se il digest smette di
  arrivare, controlla qui prima di cercare bug.
- Il workflow ha bisogno di `permissions: contents: write` per ricommittare lo stato:
  è già nel file, ma se la tua organizzazione forza i workflow in sola lettura devi
  consentirlo in *Settings → Actions → General → Workflow permissions*.

**Orari.** Il run parte lunedì alle `06:20` UTC — le **08:20 italiane d'estate**,
07:20 d'inverno — e le email partono subito dopo la pubblicazione del sito. Il cron
di GitHub non conosce i fusi né l'ora legale: se ti servono orari locali fissi tutto
l'anno, sposta il `cron` di un'ora ai cambi d'ora. Il `cron` è in
`.github/workflows/digest-settimanale.yml`.

**L'orario è indicativo, e non di poco.** GitHub accoda gli scheduled workflow e
sotto carico li fa slittare di **ore** (il 2026-07-20: 2h48). Il lunedì mattina UTC
è la fascia più congestionata, perché è quando parte il cron settimanale di mezzo
mondo. Non è un guasto e non c'è niente da abilitare: se il run non è partito
all'ora prevista, quasi sempre è solo in coda.

Non aspettare lunedì: *Actions → digest-settimanale → Run workflow* la lancia subito.
⚠️ **Non lanciarlo a mano se il run schedulato della settimana non è ancora arrivato**:
quello in coda partirà comunque dopo (`concurrency` accoda, non annulla) e girerebbe
due volte nello stesso giorno. Non è più distruttivo — l'archivio viene fuso, non
sovrascritto (DECISIONI sez. 15) — ma è lavoro sprecato e consuma quota del modello.

### d) Collega un hosting statico

Il sito pubblicato resta **statico**: il workflow costruisce il frontend, scrive `sito/`
e lo committa. Serve solo un host che pubblichi quella cartella del repo e ridispieghi
a ogni push — non c'è niente di specifico a un provider. La build avviene **in CI**,
non sull'host: l'hosting continua a servire file statici e basta.

**Render** (l'host su cui questa configurazione è testata): *New → Static Site* →
collega il repo → *Publish directory* = `sito/` → **nessun comando di build**. Fa
auto-deploy a ogni push, quindi quando il workflow ricommitta `sito/` il sito si
aggiorna da solo. Un *Private Service* non ha URL pubblico e **non** va bene.

**Netlify**: equivalente — *publish directory* = `sito/`, build command vuoto.

**GitHub Pages**: funziona, ma con un caveat. Se lo servi con un workflow di deploy,
quel workflow **non partirà** dopo il run settimanale: i push del job usano il
`GITHUB_TOKEN`, e i push fatti col `GITHUB_TOKEN` non innescano altri workflow. Con
Pages usa la modalità *Deploy from a branch* (che non dipende da un workflow), oppure
mettilo in conto. Render e Netlify non hanno il problema perché usano webhook esterni.

Ottenuto l'URL pubblico, riportalo in `sito.homepage_url` in `backend/config.yaml` e
committa: da lì in poi le email punteranno al tuo sito.

### e) Verifica che la prima run sia andata bene

Nell'ordine:

1. **Actions → il run**: spunta verde. Se è rosso, il log dice quale secret manca —
   gli errori di configurazione escono all'inizio, prima che il modello venga
   interrogato.
2. **Il log dello step "Genera il digest e il sito"** contiene una riga tipo
   `Digest generato (2026-07-20): 14 articoli in 3 sezioni con aggiornamenti [...]`.
   Zero articoli non è di per sé un errore (può essere una settimana povera), ma
   ripetuto suggerisce feed bloccati: vedi le note interne.
3. **Un commit nuovo** `chore(run): digest settimanale <data>` da `dra-bot`, che
   tocca `sito/` e `backend/data/`. Se il run è verde ma il commit non c'è, il job
   non ha trovato modifiche da salvare.
4. **Il sito pubblico** mostra la nuova data. Se il commit c'è ma il sito è vecchio,
   il problema è nel collegamento dell'host, non nella pipeline.
5. **Le email**: se hai configurato SMTP, arriva una mail ai `DIGEST_RECIPIENTS`
   (notifica se ci sono aggiornamenti, altrimenti reminder — sempre una, mai zero).
   Senza SMTP, la trovi stampata nel log del run: è il modo più rapido per provare
   tutto il resto senza configurare la posta.
6. **Le righe `[attenzione]`** nello stesso log (`gh run view --log --job=<id> |
   grep -F "[attenzione]"`). Un run **verde** può comunque aver fatto il grosso del
   lavoro con un modello di ripiego: la cascata è progettata per non fermarsi, e
   quindi degrada in silenzio. Queste righe dicono *quale* modello ha ceduto e
   *perché* (quota, formato, rete). Se la qualità delle sintesi sembra bassa,
   guarda qui **prima** di ipotizzare la causa: due diagnosi sbagliate sono nate
   dall'aver indovinato invece di leggere (DECISIONI §19 e §21).

Vuoi provare prima di toccare GitHub? *[Avvio — in locale](#avvio--in-locale)* fa
girare la stessa pipeline sulla tua macchina; ti bastano `GROQ_API_KEY` e
`DIGEST_RECIPIENTS` in un file `.env` (vedi `.env.example`).

---

## Avvio — in locale

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r backend/requirements.txt

cd backend
python -m pytest -q                # test offline, modello LLM e SMTP mockati

cp ../.env.example ../.env         # inserisci GROQ_API_KEY, DIGEST_RECIPIENTS, HOMEPAGE_URL
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
  `DIGEST_RECIPIENTS`; `HOMEPAGE_URL` qui vale `http://localhost:8080` di default,
  cioè il sito servito da `web`) e scrive `data.json` + `index.html` nel volume `sito`.
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
ogni lunedì alle **06:20 UTC** (e a mano da *Actions → Run workflow*):

**Orari.** Il cron di GitHub ragiona solo in UTC: `06:20` sono le **08:20 italiane
d'estate** e le 07:20 d'inverno. Per tenere fisso l'orario locale tutto l'anno il
cron va spostato di un'ora ai cambi d'ora. Gli orari sono comunque indicativi — e
lo slittamento può essere di **ore**, non di minuti (vedi sopra).

Il run è in **due fasi**: prima genera e pubblica il sito, poi manda le email. In
quest'ordine perché l'email rimanda al sito: si mette online la pagina e solo dopo
si manda il link. Sono due step sequenziali dello stesso job, quindi l'ordine è
garantito senza bisogno di attese.

> Se stai configurando il repo per la prima volta nel tuo account, parti da
> **[Adottare il repo](#adottare-il-repo)**: qui sotto c'è solo come funziona il
> workflow, là c'è la procedura passo-passo.

1. I secret stanno in *Settings → Secrets and variables → Actions*: `GROQ_API_KEY`
   e `DIGEST_RECIPIENTS` sono obbligatori (elenco completo in
   *[Adottare il repo](#adottare-il-repo)*).
2. Il job genera digest + `sito/` (`data.json` + `index.html` + `metriche.json`), lo
   allega come artifact e **ricommitta** lo stato (`backend/data/seen.sqlite3`,
   `backend/data/archivio/`, `backend/data/metriche/`) e `sito/` nel repo, così il
   dedup ricorda gli articoli già pubblicati e la dashboard conserva lo storico.
3. **Pubblicazione.** Il workflow non conosce l'host: si limita a ricommittare
   `sito/`. Pubblicare vuol dire collegare al repo un hosting statico qualsiasi che
   serva quella cartella e ridispieghi a ogni push, poi impostare
   `sito.homepage_url` in `config.yaml` con l'URL ottenuto. Scelta dell'host e
   caveat in *[Adottare il repo](#adottare-il-repo)*.

## Interfaccia web (frontend/)

L'interfaccia è una **single-page app React** (build con Vite), separata dal backend
Python (`backend/src/`, `backend/main.py`). **Legge `data.json`** (prodotto dal
backend) e genera lato client: home → cronologia tema → articolo con "Perché conta"
e nota preprint. In home compaiono solo i temi con aggiornamenti della settimana,
box **autocentrati**, badge "Nuovo" (≤ `badge_giorni`) e finestra settimana
(≤ `settimana_giorni`) calcolati lato client dalle date assolute in `data.json`.
Ogni digest riporta un **tempo di lettura stimato** ("~N min di lettura", ~200
parole/minuto): calcolato dal backend e salvato nell'indice, così compare già sulla
card del digest (oltre che nella testata di lettura).

Aprendo un digest, il pulsante **"Scarica PDF"** genera al volo il PDF di quel giorno
(tema + data) e lo scarica: pensato per leggerlo **offline, sul telefono**. Il PDF è
costruito **lato browser** dai dati già in memoria (testo selezionabile, fonti con link,
non uno screenshot) con **jsPDF da npm**, impacchettata nel bundle (nessuna CDN a
runtime). Il modulo PDF si carica **solo al primo click** su Scarica: jsPDF si porta
dietro ~230 kB di dipendenze che non useremmo mai per chi legge e basta. Se è configurato `sito.invio_email_url` (l'URL del Worker, vedi sotto) compare
anche **"Invia via email"**: il sito manda il PDF a un **Cloudflare Worker** che lo inoltra
a **Resend** (HTTP API, **senza SMTP**) come allegato — la API key vive solo nel Worker.
Codice e guida di deploy in [`worker/`](worker/README.md); razionale in
[`DECISIONI.md`](DECISIONI.md) §13.

Dalla home si apre anche **Sotto il cofano**, una dashboard di osservabilità che legge `metriche.json`
e mostra — con un filtro per periodo (ultimo run / 30-90 giorni / 12 mesi / intervallo
personalizzato, lo stesso pattern del calendario della cronologia) — stato delle fonti
(ok/fallito e run consecutivi falliti), costi (token e € stimati), statistiche di
deduplica e copertura dei 5 sotto-temi. Se `metriche.json` non c'è ancora (es. servendo
la sola build senza dati) mostra lo stato vuoto.

Stile "KVAdra": tema quasi-nero, accento rosa/rosso, card glass, **sfondo ripreso da
kakashi.ventures** (gli 8 simboli reali del sito, incorporati e disposti sparsi su
canvas, che si accendono di rosso vicino al cursore), homepage compatta in una sola
schermata, logo placeholder KVA.

L'interfaccia va **costruita** prima di poterla servire (`cd frontend && npm run build`:
la build finisce in `frontend/dist/`, che non è nel repo). Per vederla con i dati reali
serve `data.json` accanto a `index.html`: generarlo con `python main.py` e servire
`sito/` (vedi *Avvio — in locale*), oppure via Docker:

```bash
cd frontend && npm run build       # necessario per il servizio 'anteprima'
docker compose up anteprima        # sola interfaccia, senza dati → http://localhost:8082
docker compose up web              # sito generato con i dati → http://localhost:8080
```

Il servizio `generator` costruisce il frontend **da solo** (Dockerfile multi-stage):
il `npm run build` qui sopra serve unicamente all'anteprima.

---

## Stato

Tutte le 8 fasi sono implementate, più la **dashboard di osservabilità**
(metriche operative per run); la suite conta **211 test Python verdi** (`cd backend && pytest`) piu' **63 test
del frontend** (`cd frontend && npm test`), che coprono livello dati, export PDF,
popover di download, pannello deduplica della dashboard e rotta nell'URL. Le scelte di
progetto e il perché sono in [`DECISIONI.md`](DECISIONI.md).

Punti noti, non bloccanti, che chi adotta il repo farà bene a tenere d'occhio:

- i feed possono rispondere diversamente da un IP cloud (possibile anti-bot): se una
  fonte sparisce per più run di fila arriva una nota interna;
- la soglia di dedup (`soglia_overlap_dedup`, 0.7) e l'elenco di entità note sono
  calibrati sul nostro flusso: su un beat diverso vanno ritarati;
- le fonti in `config.yaml` sono scelte per il beat *"Infrastruttura & Hardware AI"*;
  cambiando tema vanno sostituite;
- **la quota del free tier è il vincolo dominante**, non il costo in euro: in un run
  pieno (~113 chiamate) il modello primario si esaurisce dopo pochi minuti e la
  cascata scende ai modelli di ripiego, con sintesi di qualità inferiore. Le righe
  `[attenzione]` nel log lo dicono; un run leggero (~13 chiamate) resta invece
  interamente sul primario. È il motivo per cui `MAX_ESTRATTO_CHARS` è tenuto basso
  ([`DECISIONI.md`](DECISIONI.md) §21).

## Test

```bash
cd backend && python -m pytest -q     # 211 test
cd frontend && npm test               # 63 test (Vitest)
```

Ogni fase è coperta da test basati sugli scenari Given/When/Then del documento di
progettazione (sez. 16–18). Un commit avviene solo a test verdi.

Il workflow settimanale esegue **entrambe** le suite prima di generare il digest: i
test del frontend girano subito dopo `npm run build`, così una regressione
nell'interfaccia ferma il run invece di finire pubblicata sul sito.