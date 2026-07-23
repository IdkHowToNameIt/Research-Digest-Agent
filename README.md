# Research Digest Agent — DRA

Digest settimanale sul beat **Infrastruttura & Hardware AI** (chip, data center,
energia, supply chain, cloud capacity): ogni run monitora le fonti RSS/Atom
configurate e produce un **digest a 5 sezioni fisse**, consegnato via **email di
notifica** + **sito statico**.

La pipeline è **~80% codice deterministico / ~20% modello**: fetch, filtri,
dedup, classificazione e assemblaggio sono script; il modello LLM (Groq)
interviene solo sui testi e non sceglie mai le fonti né inventa URL.

## Documentazione

| Documento | Contenuto |
|---|---|
| [`DECISIONI.md`](DECISIONI.md) | Le scelte di progetto e il loro perché, con misure |
| [`worker/README.md`](worker/README.md) | Deploy del Worker per l'invio del PDF via email |

Questo README copre solo l'**operatività**: adottare il repo, farlo girare,
verificarlo. Manuale utente e documentazione analitica sono forniti a parte.

## Struttura del progetto

```
backend/            pipeline Python (batch settimanale)
├── main.py         entrypoint: --fase tutto | genera | email
├── config.yaml     fonti, temi, dedup, finestre, prezzi
├── src/            raccolta/ (fetch, filtri, dedup) · modello/ (Groq) · consegna/ (sito, email)
├── data/           stato: seen.sqlite3, archivio/, metriche/ (committati dalla CI)
└── tests/          215 test offline (LLM e SMTP mockati)

frontend/           interfaccia React + Vite (63 test Vitest)
sito/               cartella pubblicata dall'hosting statico (generata, committata dalla CI)
worker/             Cloudflare Worker per l'invio email del PDF (opzionale)
.github/workflows/  digest-settimanale.yml (il run settimanale)
```

## Adottare il repo

A regime gira da solo: la Action settimanale esegue la pipeline, ricommitta i
risultati, e l'hosting statico ripubblica a ogni push. Nessun server da gestire.

### 1. Prendi il repo

Fork, oppure clone + push su un repo tuo. Arriva con lo storico dei nostri
digest: per ripartire da zero svuota `backend/data/archivio/`,
`backend/data/metriche/`, `backend/data/seen.sqlite3` e `sito/` — la prima run
li ricrea.

### 2. Secret e variabile

*Settings → Secrets and variables → Actions*. Nessun default silenzioso: se
manca un obbligatorio, il run si ferma con un errore che dice quale.

| Secret | Obbligatorio | Note |
|---|---|---|
| `GROQ_API_KEY` | **Sì** | gratis su [console.groq.com/keys](https://console.groq.com/keys) |
| `DIGEST_RECIPIENTS` | **Sì** | lettori del digest, indirizzi separati da virgola |
| `INTERNAL_NOTES_RECIPIENTS` | solo per le note interne | chi gestisce il sistema — lista **separata** dai lettori, apposta |
| `SMTP_USER` / `SMTP_PASS` | No | senza, le email vengono solo stampate a log. Con Gmail `SMTP_PASS` è una **App Password** a 16 cifre, non la password dell'account |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | No | default Gmail: `smtp.gmail.com`, `587`, mittente = `SMTP_USER` |

E una **variabile** (scheda *Variables*, non Secrets):

| Variabile | Obbligatoria | Valore |
|---|---|---|
| `HOMEPAGE_URL` | **Sì** | l'URL pubblico del sito (lo ottieni al punto 4): è il link che l'email manda ai lettori |

### 3. Abilita la Action

Su un fork le Action sono disabilitate di default: vai su *Actions* e conferma.
Tre caveat:

- GitHub **disattiva gli scheduled workflow dopo 60 giorni di inattività** del
  repo: se il digest smette di arrivare, controlla qui prima di cercare bug.
- Il cron (lunedì **06:20 UTC**) può slittare di **ore** sotto carico: non è un
  guasto, il run è in coda. Non rilanciarlo a mano se quello schedulato non è
  ancora arrivato (girerebbe due volte).
- Il workflow richiede `permissions: contents: write` (già nel file); se
  l'organizzazione forza la sola lettura, consentilo in *Settings → Actions*.

### 4. Collega un hosting statico

Serve solo un host che pubblichi la cartella `sito/` del repo e ridispieghi a
ogni push. **Render** (testato): *New → Static Site* → publish directory
`sito/`, **nessun build command**. Netlify equivalente. GitHub Pages funziona
solo in modalità *Deploy from a branch* (i push della CI usano il
`GITHUB_TOKEN`, che non innesca altri workflow). Ottenuto l'URL, mettilo in
`HOMEPAGE_URL`.

### 5. Verifica la prima run

1. *Actions* → run verde (se rosso, il log dice quale secret manca);
2. un commit nuovo `chore(run): digest settimanale <data>` di `dra-bot`;
3. il sito pubblico mostra la nuova data;
4. l'email arriva (o, senza SMTP, sta nel log del run);
5. le righe `[attenzione]` nel log: un run verde può aver ripiegato su un
   modello di riserva — quelle righe dicono quale e perché.

## Avvio in locale

```bash
python -m venv .venv && .venv\Scripts\activate    # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env                               # GROQ_API_KEY, DIGEST_RECIPIENTS, HOMEPAGE_URL

cd backend
python -m pytest -q            # 215 test, nessuna API key richiesta
python main.py --config config.yaml
python -m http.server -d ../sito 8080              # il sito usa fetch(): serve http, non file://
```

> **Python 3.14**: se `pydantic` non importa, `pip install --force-reinstall
> --no-cache-dir pydantic`. Con Docker non succede (immagine su Python 3.12).

## Avvio con Docker

```bash
export GROQ_API_KEY=...                    # PowerShell: $env:GROQ_API_KEY="..."
export DIGEST_RECIPIENTS=tu@example.com
docker compose up --build                  # genera e serve su http://localhost:8080
```

`docker compose down -v` rimuove anche i volumi (sito + storico).

## Il workflow

- **`digest-settimanale.yml`** — il run (cron lunedì 06:20 UTC + manuale).
  Due fasi nello stesso job: `--fase genera` (pipeline + sito + commit dello
  stato) poi `--fase email` — prima si pubblica, poi si manda il link.
  Per modifiche alla sola interfaccia, un workflow che ricompilava `frontend/`
  senza rifare il digest è stato rimosso il 2026-07-23: recuperabile dallo
  storico git (`pubblica-frontend.yml`) se il frontend torna a evolvere.

## Test

```bash
cd backend && python -m pytest -q     # 215 test
cd frontend && npm test               # 63 test (Vitest)
```

Il workflow esegue entrambe le suite prima di pubblicare: una regressione ferma
il run invece di finire sul sito.

## Punti noti

- I feed possono rispondere diversamente da un IP cloud (anti-bot): se una
  fonte sparisce per più run arriva una nota interna.
- Soglia di dedup ed entità note sono calibrate su questo beat: su un beat
  diverso vanno ritarate, e le fonti in `config.yaml` sostituite.
- **La quota del free tier è il vincolo dominante**, non il costo: in un run
  pieno la cascata può scendere ai modelli di ripiego (sintesi più povere).
  Le righe `[attenzione]` nel log lo dicono; dettagli in `DECISIONI.md` §21.
