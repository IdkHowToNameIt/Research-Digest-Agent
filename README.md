# Research Digest Agent — DRA

Beat: **Infrastruttura & Hardware AI** (chip NVIDIA/AMD/silicio custom, data
center, consumo energetico, colli di bottiglia della supply chain, cloud provider
e capacità di calcolo).

Agente che, ogni settimana, monitora 12 fonti RSS/Atom pubbliche e produce un
**digest strutturato** su 5 sotto-temi fissi, consegnato via **email di notifica**
+ **sito web interno**. Target: CTO, investitori infrastrutturali, chi vuole
capire i vincoli reali dietro le promesse dei modelli.

Documento di progettazione completo (motivazioni + scenari Given/When/Then):
vedi Notion (link nel `CLAUDE.md`). Le regole vincolanti sono in `CLAUDE.md`.

## Principi vincolanti (sintesi)

- **Mai contenuto inventato o forzato.** Sezione senza materiale → nota di stato
  esplicita, mai riempita artificialmente.
- **Dati quantitativi** (capex, energia) riportati solo se citati testualmente
  dalla fonte, mai riformulati/arrotondati dal modello.
- **~80% script / 20% modello**: il modello (Gemini) è riservato alla sola
  sintesi finale; raccolta, classificazione, dedup e assemblaggio sono codice
  deterministico.
- **`note_interne`** generato solo da script, mai esposto nel digest pubblico.

## Architettura

Il digest è modellato come **5 sezioni fisse** (una per sotto-tema), sempre
presenti anche se vuote, ciascuna con uno `stato` esplicito
(`con_aggiornamenti` / `nessun_aggiornamento`). Pipeline:

```
fetch (12 fonti, fail-soft, troncamento per fonte)
  → classificazione (articolo → 1 dei 5 temi o null; filtro rilevanza a monte)
  → deduplicazione (hash esatto + overlap fuzzy + 3 segnali di novità)
  → sintesi (Gemini, solo campi testuali degli articoli)
  → assemblaggio Digest (schema validato)
  → consegna (email di notifica + sito web interno)
```

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
├── state.py          memoria persistente (SQLite): dedup + conteggi run
└── tools/
    ├── fetch.py      raccolta RSS/Atom, stati fetch, troncamento         [Fase 2]
    ├── dedup.py      anti-duplicati esatto + fuzzy + segnali            [Fase 4]
    └── deliver.py    consegna Markdown (email/sito — Fasi 7-8)          [Fase 6]
config.yaml           beat, 12 fonti, parametri dedup
tests/                test deterministici (offline, Gemini mockato)
claude-progress.txt   log di avanzamento per sessione
```

## Avvio (sviluppo)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m pytest -q                # suite di test (nessuna rete, nessuna API key)
python main.py --demo             # run offline: sintesi deterministica, scrive out/digest.md
```

> Nota Python 3.14: se `pydantic` non importa (`_pydantic_core` mancante),
> reinstallalo con `pip install --force-reinstall --no-cache-dir pydantic`
> (un wheel cp311 in cache non è compatibile).

Per la modalità con modello (Gemini): `cp .env.example .env` e inserisci
`GEMINI_API_KEY`, poi `python main.py`. I test della suite **mockano sempre le
chiamate al modello**: non serve una API key per svilupparli.

## Stato di avanzamento (per fasi)

| Fase | Contenuto | Stato |
|------|-----------|:-----:|
| 1 | Schema dati (5 sezioni fisse, enum, note_interne) | ✅ |
| 2 | Fonti, config, fetch + troncamento differenziato | ✅ |
| 3 | Classificazione sotto-temi + filtro rilevanza | ✅ |
| 4 | Deduplicazione (hash + fuzzy + 3 segnali novità) | ✅ |
| 5 | Note interne (fetch_failed ×3, energia 0 ×3) | ✅ |
| 6 | Criteri editoriali + sintesi Gemini + orchestrazione | ✅ |
| 7 | Email (notifica / reminder) | ⏳ |
| 8 | Sito web interno | ⏳ |

Dettaglio per sessione: `claude-progress.txt`.

## Test

```bash
python -m pytest -q
```

Ogni fase aggiunge test basati sugli scenari Given/When/Then del documento di
progettazione (sez. 16-17). Un commit avviene solo a test verdi.
