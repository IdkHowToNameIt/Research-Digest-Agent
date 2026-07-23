# Research Digest Agent — DRA

Digest settimanale sul beat **Infrastruttura & Hardware AI** (chip, data center,
energia, supply chain, cloud capacity): ogni run monitora le fonti RSS/Atom
configurate e produce un digest a 5 sezioni fisse, consegnato via email di
notifica + sito statico.

La pipeline è **~80% codice deterministico / ~20% modello**: fetch, filtri,
dedup, classificazione e assemblaggio sono script; il modello LLM (Groq)
interviene solo sui testi e non sceglie mai le fonti né inventa URL.

Questo README copre solo l'operatività: adottare il repo, farlo girare,
verificarlo. Il deploy del Worker per l'invio del PDF via email è in
[`worker/README.md`](worker/README.md); manuale utente e documentazione
analitica sono forniti a parte.

## Struttura del progetto

```
backend/            pipeline Python (batch settimanale)
├── main.py         entrypoint: --fase tutto | genera | email
├── config.yaml     fonti, temi, dedup, finestre, prezzi
├── src/            raccolta/ (fetch, filtri, dedup) · modello/ (Groq) · consegna/ (sito, email)
├── data/           stato: seen.sqlite3, archivio/, metriche/ (committati dalla CI)
└── tests/          217 test offline (LLM e SMTP mockati)

frontend/           interfaccia React + Vite (63 test Vitest)
sito/               cartella pubblicata dall'hosting statico (generata, committata dalla CI)
worker/             Cloudflare Worker per l'invio email del PDF (opzionale)
.github/workflows/  digest-settimanale.yml (il run settimanale)
```

## Adottare il repo

A regime gira da solo: la Action settimanale (cron lunedì 06:20 UTC + manuale)
esegue la pipeline in due fasi — `--fase genera` (digest + sito + commit dello
stato) poi `--fase email` — e l'hosting statico ripubblica a ogni push.

1. **Prendi il repo** — fork, oppure clone + push su un repo tuo. Per ripartire
   da zero svuota `backend/data/archivio/`, `backend/data/metriche/`,
   `backend/data/seen.sqlite3` e `sito/`: la prima run li ricrea.

2. **Secret e variabile** — *Settings → Secrets and variables → Actions*.
   Nessun default silenzioso: se manca un obbligatorio, il run si ferma
   dicendo quale.

   | Secret | Obbligatorio | Note |
   |---|---|---|
   | `GROQ_API_KEY` | **Sì** | gratis su [console.groq.com/keys](https://console.groq.com/keys) |
   | `DIGEST_RECIPIENTS` | **Sì** | lettori del digest, indirizzi separati da virgola |
   | `INTERNAL_NOTES_RECIPIENTS` | solo per le note interne | chi gestisce il sistema — lista **separata** dai lettori |
   | `SMTP_USER` / `SMTP_PASS` | No | senza, le email vengono solo stampate a log. Con Gmail `SMTP_PASS` è una **App Password** a 16 cifre (si rigenera se cambi la password dell'account) |
   | `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | No | default Gmail: `smtp.gmail.com`, `587`, mittente = `SMTP_USER` |

   E una **variabile** (scheda *Variables*): `HOMEPAGE_URL` = l'URL pubblico del
   sito, il link che l'email manda ai lettori.

3. **Abilita la Action** — su un fork sono disabilitate di default (*Actions* →
   conferma). GitHub spegne gli scheduled workflow dopo 60 giorni di inattività
   del repo; il cron può slittare di ore sotto carico (non è un guasto, non
   rilanciare a mano); serve `permissions: contents: write` (già nel file).

4. **Collega un hosting statico** — un host qualsiasi che pubblichi la cartella
   `sito/` a ogni push. **Render** (testato): *New → Static Site*, publish
   directory `sito/`, nessun build command. Ottenuto l'URL, mettilo in
   `HOMEPAGE_URL`.

5. **Verifica la prima run** — run verde su *Actions*, commit nuovo di
   `dra-bot`, sito con la nuova data, email arrivata (o nel log, senza SMTP).
   Le righe `[attenzione]` nel log segnalano i ripieghi su modelli di riserva.

## Avvio in locale

```bash
python -m venv .venv && .venv\Scripts\activate    # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env                               # GROQ_API_KEY, DIGEST_RECIPIENTS, HOMEPAGE_URL

cd backend
python -m pytest -q                                # 217 test, nessuna API key richiesta
python main.py --config config.yaml
python -m http.server -d ../sito 8080              # il sito usa fetch(): serve http, non file://
```

Test frontend: `cd frontend && npm test` (63 test Vitest). Il workflow esegue
entrambe le suite prima di pubblicare: una regressione ferma il run.

## Con Docker

Utile per far girare il digest su una macchina che non è GitHub (VM, server
interno) o per provarlo senza installare Python: gli stessi due pezzi del run
in CI, un container che genera e uno che serve.

```bash
cp .env.example .env          # oppure: export GROQ_API_KEY=... DIGEST_RECIPIENTS=...
docker compose up --build     # sito su http://localhost:8080
```

| Servizio | Cosa fa |
|---|---|
| `generator` | esegue la pipeline **una volta** e termina (è un batch, non un server) |
| `web` | nginx che serve `sito/`; parte solo se il generator è finito bene |
| `anteprima` | solo l'interfaccia, senza rigenerare il digest — `docker compose up anteprima` su :8082. Richiede `cd frontend && npm run build` (la build non è nel repo) |

Lo stato vive in due volumi Docker (`data` = `seen.sqlite3` + archivio,
`sito` = output pubblicato): sopravvivono ai riavvii, e cancellarli equivale a
ripartire da zero. Senza `SMTP_USER`/`SMTP_PASS` le email vengono solo stampate
a log — comodo per una prova. Per un run periodico basta un cron sull'host che
chiami `docker compose run --rm generator`.

## Punti noti

- I feed possono rispondere diversamente da un IP cloud (anti-bot): se una
  fonte sparisce per più run arriva una nota interna.
- Soglia di dedup, entità note e fonti in `config.yaml` sono calibrate su
  questo beat: su un beat diverso vanno ritarate.
- **La quota del free tier è il vincolo dominante**, non il costo: in un run
  pieno la cascata può ripiegare su modelli di riserva (righe `[attenzione]`
  nel log). Per lo stesso motivo `MAX_ESTRATTO_CHARS` è tenuto a 8000.
- **Un sito statico gratuito è sempre pubblico**: chi ha l'URL vede digest e
  dashboard, e un repo pubblico espone comunque l'archivio. Per limitare
  l'accesso servono un dominio proprio con Cloudflare Access, oppure la
  pubblicazione della cartella `sito/` su un web server in intranet — in
  entrambi i casi senza toccare il codice.
- Ogni pezzo (esecuzione, LLM, hosting, email) si sostituisce da solo, via
  secret e variabili: nessuna di queste scelte è cablata nel codice.