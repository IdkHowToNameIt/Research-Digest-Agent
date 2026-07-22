# DRA — Come funziona

Panoramica funzionale del Digest Research Agent: cosa fa il sito, cosa succede
durante un run, quali script compongono la pipeline e a cosa serve ciascuno.
Documento descrittivo, senza dettagli di codice; le motivazioni delle scelte
stanno in `DECISIONI.md`.

## 1. Cosa fa, in breve

DRA produce un **digest settimanale** sul beat *Infrastruttura & Hardware AI*,
organizzato in **5 sotto-temi fissi**: chip, data center, energia, supply chain,
cloud capacity. Ogni run raccoglie le notizie dalle fonti configurate, le filtra,
le deduplica, le sintetizza con un modello LLM e pubblica il risultato su due
canali: un **sito statico** e una **email di notifica**.

La pipeline è **~80% script deterministico**: il modello interviene solo sui
testi (sintesi, "perché conta", etichette dei gruppi). Metadati, filtri,
classificazione e assemblaggio sono tutti codice, testabile e riproducibile.

## 2. Il sito

Sito statico pubblicato su Render (host intercambiabile: serve i file della
cartella `sito/`, che vengono committati nel repository). Il backend **non
genera HTML**: scrive dei file JSON (il contratto dati) e il frontend React
costruisce le pagine lato client leggendoli.

Funzionalità:

- **Home** — un riquadro per ognuno dei 5 temi, con lo stato della settimana:
  aggiornamenti presenti oppure "nessun aggiornamento" (stato esplicito, mai
  una sezione mancante).
- **Cronologia per tema** — l'elenco dei gruppi-giorno di un tema: le notizie
  dello stesso tema uscite nello stesso giorno confluiscono in un gruppo con
  un titolo riassuntivo.
- **Dettaglio del gruppo** — le notizie del giorno con sintesi, "perché conta"
  e i link alle fonti originali. Un segnaposto di lettura segue lo scorrimento.
- **Filtro per periodo** — restringe la cronologia a un intervallo di date.
- **Scarica il digest** — esporta il digest corrente in PDF, generato nel
  browser (nessun server coinvolto); predisposto anche l'invio via email
  dietro feature-flag.
- **"Sotto il cofano"** — la dashboard di osservabilità: per ogni run mostra lo
  stato delle fonti, le statistiche di deduplica, la copertura dei 5 temi, il
  costo stimato delle chiamate al modello e le eventuali segnalazioni (es.
  sezione energia a zero per run consecutivi).
- **Sfondo interattivo** — replica dell'effetto di kakashi.ventures: griglia di
  glifi con simulazione d'acqua che reagisce al cursore e al click. È solo
  presentazione: si disattiva sopra i contenuti e ha un interruttore per le
  macchine senza accelerazione grafica.

La navigazione usa la rotta nell'URL: refresh e "indietro" del browser
mantengono la pagina corrente.

## 3. Il run: quando parte e cosa succede

Due modi di partire, entrambi definiti in `.github/workflows/`:

- **`digest-settimanale.yml`** — il run vero. Parte **ogni lunedì alle 06:20
  UTC** (il cron di GitHub può slittare di ore: non è un guasto) oppure a mano
  dalla scheda Actions. Due fasi in sequenza:
  1. **`--fase genera`**: pipeline completa → digest + JSON del sito. Lo stato
     (archivio, database dei visti, metriche, `sito/`) viene committato e
     pushato; Render rileva il push e ridispiega il sito.
  2. **`--fase email`**: legge il digest appena generato e invia le email.
     L'ordine è voluto: l'email rimanda al sito, quindi il sito deve essere
     già aggiornato quando l'email arriva.
- **`pubblica-frontend.yml`** — pubblicazione **solo interfaccia**, senza
  digest: ricostruisce il bundle del frontend e lo ricopia in `sito/` senza
  toccare i JSON dei dati. Parte da solo sui push che modificano `frontend/`
  (~25 secondi, zero chiamate al modello). Serve per mettere live una modifica
  di pagina senza rifare la raccolta.

Dentro la fase genera, la pipeline esegue nell'ordine:

1. **Raccolta** — lettura dei feed RSS/Atom delle fonti configurate; ogni fonte
   ha un esito esplicito (riuscita, anche con zero voci, oppure fallita).
2. **Filtro di rilevanza** — per le sole fonti generaliste (vedi §4).
3. **Deduplica** — contro lo storico e tra i candidati del run (vedi §4).
4. **Classificazione e raggruppamento** — assegnazione al tema e formazione
   dei gruppi-giorno.
5. **Note interne** — controlli operativi che possono generare segnalazioni al
   comparto IT (mai mostrate ai lettori).
6. **Sintesi** — il modello scrive i testi; i metadati restano quelli reali.
7. **Pubblicazione** — scrittura dei JSON del sito, dell'archivio del giorno e
   delle metriche del run.

Ogni run produce anche un **record di metriche** (un file JSON per run), da cui
il sito costruisce la dashboard.

## 4. Gli script dei filtri

I filtri sono il cuore della parte deterministica: decidono cosa entra nel
digest prima che il modello veda alcunché.

- **`backend/src/raccolta/classify.py`** — due compiti:
  - *Filtro di rilevanza*: le fonti **generaliste** (Tom's Hardware, Google
    Cloud Blog) pubblicano anche contenuti fuori beat (offerte, gadget,
    database, sicurezza). Un articolo passa solo se contiene almeno una parola
    del beat (chip, data center, capacità, energia…), con confronto ancorato
    all'inizio di parola per non far scattare falsi positivi dentro altre
    parole. In più, se il **titolo** annuncia una storia di cybersicurezza
    (hack, breach, malware…), la voce è scartata anche se il testo tocca
    parole del beat: è cronaca di sicurezza, non hardware. Le fonti curate
    (blog ufficiali dei vendor) non passano da questo filtro.
  - *Classificazione*: il tema di un articolo segue la **fonte di
    provenienza** (mappa fonte → tema nella configurazione), non una
    valutazione del contenuto. Ogni articolo finisce in esattamente un tema,
    o in revisione manuale.
- **`backend/src/raccolta/dedup.py`** — deduplicazione su due livelli:
  - *esatta*: hash su titolo normalizzato + URL contro tutto lo storico;
  - *fuzzy*: nella finestra delle 4–6 settimane, similarità di parole ed
    entità (indice di Jaccard) con segnali di novità, per distinguere "stessa
    notizia ripresa" da "sviluppo nuovo". Per gli aggregatori (Google News),
    dove le varianti della stessa notizia arrivano da testate diverse, il
    raggruppamento usa una chiave azienda + cifra.
- **`backend/src/raccolta/fetch.py`** — la raccolta vera e propria: legge i
  feed, tronca gli estratti alla lunghezza configurata e distingue una fonte
  rotta da una fonte semplicemente silenziosa.

## 5. Gli altri script del backend

- **`backend/main.py`** — punto d'ingresso: orchestra le fasi (`tutto`,
  `genera`, `email`) e fa i controlli di configurazione all'avvio (fail-fast:
  niente valori di default silenziosi su destinatari e URL).
- **`backend/src/pipeline.py`** — l'orchestrazione della sequenza descritta al
  §3: collega raccolta, filtri, sintesi e assemblaggio.
- **`backend/src/schemas.py`** — lo schema dati (Pydantic) del digest: 5
  sezioni sempre presenti, stati vuoti espliciti, note interne separate dal
  contenuto pubblico.
- **`backend/src/config.py`** — caricamento e validazione di `config.yaml`
  (fonti, temi, troncamenti, finestra di attualità).
- **`backend/src/state.py`** — la memoria persistente (SQLite): storico degli
  articoli già riportati (per la deduplica) e contatori dei run consecutivi
  (per le note interne).
- **`backend/src/metriche.py`** — raccoglie le metriche operative del run
  (stato fonti, dedup, copertura, token e costo del modello) e le persiste.
- **`backend/src/modello/llm.py`** — l'adattatore verso Groq: gestisce la
  cascata di modelli (se uno è saturo o fallisce si passa al successivo e ci
  si "appiccica" a quello funzionante), i retry e il parsing tollerante delle
  risposte.
- **`backend/src/modello/prompts.py`** — i prompt: al modello si chiedono solo
  testi, con l'obbligo di restare sui fatti forniti (nessun link o dato
  inventato).
- **`backend/src/modello/sintesi.py`** — applica il modello agli articoli e
  assembla il digest; ha un fallback senza modello per demo e test.
- **`backend/src/consegna/sito.py`** — scrive i JSON del sito (dati per tema,
  archivio aggregato, metriche per la dashboard) e copia il bundle del
  frontend nella cartella di pubblicazione.
- **`backend/src/consegna/notifica.py`** — le email: una sola ai lettori a
  settimana (notifica se c'è qualcosa, reminder altrimenti), con rimando alla
  homepage; le eventuali note interne viaggiano in un'email separata al
  comparto IT. Invio via SMTP se configurato, altrimenti solo a log.
- **`backend/src/consegna/note_interne.py`** — genera le segnalazioni
  operative: fonte in errore da N run consecutivi, sezione energia a zero da
  N run consecutivi. Solo script, mai il modello; mai nel digest pubblico.
- **`backend/src/consegna/deliver.py`** — il digest in Markdown, per debug e
  anteprima.

## 6. Gli script del frontend

- **`frontend/src/App.jsx` + `componenti/`** — le viste: home, cronologia,
  dettaglio, dashboard, intestazione, filtro periodo, esportazione.
- **`frontend/src/dati.js`** — caricamento e aggregazione dei JSON pubblicati.
- **`frontend/src/rotta.js`** — la rotta nell'URL (refresh e cronologia del
  browser funzionano).
- **`frontend/src/lettura.js`** — il segnaposto di lettura che segue lo
  scorrimento.
- **`frontend/src/pdf.js`** — l'esportazione del digest in PDF nel browser.
- **`frontend/src/sfondo.js`** — lo sfondo interattivo (griglia di glifi +
  simulazione d'acqua + anelli sul click).
- **`frontend/src/scorrimento.js`, `effetti.js`** — scorrimento morbido e
  comparsa delle sezioni allo scroll.

I test (63 nel frontend, 215 nel backend) girano a ogni pubblicazione: se
falliscono, non si pubblica.

## 7. Configurazione e dati

La configurazione **fuori dal repository** sta nei Secret/Variable di GitHub:
chiave del modello (`GROQ_API_KEY`), destinatari del digest e delle note
interne (liste separate), URL della homepage, credenziali SMTP opzionali.
`config.yaml` tiene il resto: fonti con tema e troncamento, finestra di
attualità, cartelle di output.

I dati vivono in due posti:

- `backend/data/` — lo stato dell'agente: database dei visti, archivio
  giornaliero, metriche per run;
- `sito/` — ciò che il sito serve: JSON dei dati + bundle del frontend.

Entrambi vengono committati dal run: il repository è anche il meccanismo di
pubblicazione (l'host statico serve i file committati).
