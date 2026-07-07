# KVA Research Digest Agent — starter (Python)

Starter kit per costruire un agente che, a intervalli regolari, tiene d'occhio
alcune fonti pubbliche su un tema (il tuo *beat*) e produce un digest strutturato:
per ogni voce titolo, fonte, link, data, sintesi, motivo per cui conta e tag. Al
primo avvio produce già un digest di prova; tu lo adatti al tuo beat cambiando le
fonti in `config.yaml` e i criteri editoriali in `src/prompts.py`.

Cos'è un agente, in breve: un programma a cui dai un obiettivo e alcuni strumenti,
e che poi lascia decidere al modello linguistico (LLM, *Large Language Model*: il
"cervello" tipo Claude o GPT) quali strumenti usare e in che ordine. La differenza
con un MCP server e la spiegazione estesa sono nell'handout, sezione "Primer".

## Due modalità

Demo, senza chiave — `python main.py --demo`. Usa un feed di esempio già incluso
e regole fisse (niente modello AI), così vedi subito tutta la catena: raccolta
delle notizie, rimozione dei doppioni, sintesi, digest in formato fisso,
salvataggio del file. È il modo giusto per il primo avvio, e puoi rilanciarla
quante volte vuoi: riparte sempre pulita.

Agente, con il modello AI — `python main.py`. Qui è il modello a scegliere e
riassumere le notizie. Serve una chiave: mettila nel file `.env` (vedi sotto) e il
programma la legge da solo.

## Avvio rapido

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py --demo            # genera un digest di esempio in out/
```

Per la modalità agente:

```bash
cp .env.example .env             # poi inserisci la tua OPENAI_API_KEY nel file .env
python main.py                   # l'agente gira e produce il digest
```

(Controlla `python3 --version`: serve 3.10 o superiore. Se vedi 3.9, installa una
versione più recente e usala per la venv, es. `python3.12 -m venv .venv`.)

## Come personalizzarlo per il tuo beat

1. `config.yaml`: imposta `beat`, `beat_slug` e soprattutto le fonti. Le fonti
   sono di solito dei *feed RSS/Atom*, cioè l'indirizzo che molti siti espongono
   per far leggere in automatico i loro ultimi articoli (spesso a `/feed` o
   `/rss`). La fonte di default è un file locale di esempio, che serve a far
   funzionare la demo senza internet: sostituiscila con fonti reali.
2. `src/prompts.py`: i criteri editoriali, cioè cosa è rilevante, come scrivere la
   sintesi e la regola sulle fonti (mai inventare: ogni voce deve avere una fonte
   reale e un link che funziona).
3. (Avanzato) `src/tools/`: aggiungi o modifica gli strumenti.

## Struttura del progetto

```
agent-starter-python/
├── main.py              avvio (modalità --demo o agente)
├── config.yaml          <-- il tuo beat e le tue fonti
├── src/
│   ├── agent.py         modello + istruzioni + strumenti + output strutturato
│   ├── prompts.py       <-- i criteri editoriali (regola sulle fonti)
│   ├── schemas.py       schema controllato del digest (Pydantic)
│   ├── state.py         memoria dei doppioni (SQLite)
│   ├── config.py        caricamento della configurazione
│   └── tools/
│       ├── fetch.py     raccolta dalle fonti (RSS/Atom)
│       ├── dedup.py     filtro anti-duplicati
│       └── deliver.py   consegna del digest (Markdown)
├── tests/               test sulle parti deterministiche (girano senza internet)
├── sample-output/
│   ├── sample-feed.xml      feed di esempio (per la demo)
│   └── digest-esempio.md    esempio di digest prodotto
└── data/                memoria persistente (creata al primo avvio in modalità agente)
```

## Schedulazione (far girare l'agente da solo)

Esempi:

- cron (Linux/macOS): `0 8 * * 1 cd /percorso/agent-starter-python && .venv/bin/python main.py` (ogni lunedì alle 8:00).
- una GitHub Action programmata: trovi un template pronto in `examples/github-action-research-digest.yml` (copialo in `.github/workflows/` del tuo repository e aggiungi il segreto `OPENAI_API_KEY`).

Attenzione: sotto cron l'ambiente è "spoglio", quindi lancia il comando dalla
cartella del progetto (dove c'è il file `.env`) oppure passa la chiave nel comando,
altrimenti la chiave non viene trovata.

## Criteri di accettazione (la griglia tecnica, vedi handout)

Cosa fa già lo starter:

- [ ] Output strutturato e controllato: il digest rispetta sempre lo schema (Pydantic).
- [ ] Grounding: tiene solo le voci con un link tra le fonti raccolte; non inventa.
- [ ] Doppioni tra esecuzioni: in modalità agente non ripropone voci già riportate.
- [ ] Gestione errori di base: se una fonte non risponde, la segnala su schermo e la salta, senza bloccare il resto.
- [ ] Limite di iterazioni: l'agente si ferma dopo un numero massimo di passi (`max_turns` in `config.yaml`), così contiene tempi e costi.

Cosa resta da curare voi:

- [ ] Schedulazione e consegna: far partire l'agente in automatico (cron o GitHub Action) e consegnare dove serve.
- [ ] Stima della spesa: `max_turns` limita le iterazioni, ma non calcola gli euro. Se usate il modello AI, tenete un modello economico e annotate numero di chiamate e costo stimato.

## Test

```bash
python -m pytest -q      # verifica schema, doppioni e raccolta (senza internet)
```
