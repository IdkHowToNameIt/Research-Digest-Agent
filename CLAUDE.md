# Research Digest Agent — Infrastruttura & Hardware AI

Documento di progettazione completo (riferimento, non da rileggere ad ogni sessione): https://app.notion.com/p/396dd8775af781b6b4b2cee0a55107c8

## Progetto in una frase
Digest settimanale su 5 sotto-temi (chip, data_center, energia, supply_chain, cloud_capacity), da 12 fonti RSS/Atom, consegnato via email di notifica + sito web interno.

## Regole operative non negoziabili
- **Mai contenuto inventato o forzato.** Sezione senza materiale → nota di stato esplicita, mai riempita artificialmente.
- **Dati quantitativi (capex, energia)**: riportati solo se citati testualmente dalla fonte, mai riformulati/arrotondati dal modello.
- **`note_interne`**: generato solo da script, mai dal modello. Mai esposto pubblicamente (né sito né eventuale MCP futuro).
- **~80% script / 20% modello**: modello riservato principalmente alla sintesi finale.

## Schema dati (src/schemas.py)
```
Digest = { data_generazione, sezioni: [5 fissi], note_interne: [] }
Sezione = { tema: enum[chip, data_center, energia, supply_chain, cloud_capacity],
            stato: enum[con_aggiornamenti, nessun_aggiornamento], articoli: [] }
Articolo = { titolo, fonti: [{nome, link}], data, sintesi, perche_conta, note? }
```
- `perche_conta` sempre obbligatorio, mai vuoto.
- Stato "nessun_aggiornamento" → messaggio template fisso da codice, mai generato dal modello.

## Fonti e troncamento (config.yaml)
12 fonti finali. Nessun limite di troncamento per: arXiv, Google Cloud Blog (condizionato a filtro rilevanza tematica a monte), Google Cloud — Infrastructure. Tutte le altre 9 fonti: 500 caratteri, taglio su confine di parola.

## Deduplicazione
1. Hash esatto (titolo normalizzato + URL) su tutto lo storico.
2. Overlap fuzzy entità/parole chiave, finestra 4-6 settimane. Overlap alto + nessun segnale di novità (numero diverso, data più recente nel testo, nuova entità) → scartato come duplicato. Soglia overlap proposta 0,7 — **parametro da calibrare, non fisso**.

## Criteri editoriali (src/prompts.py)
Italiano, tono divulgativo-preciso + business/investitori. Sintesi 3-5 frasi (6-8 solo se densità informativa reale). Filtro marketing moderato su fonti corporate. Fonti senza estratto → sintesi minima dal titolo. Google News multi-testata → una voce, segnalazione esplicita. arXiv → "I risultati preliminari di uno studio indicano che..." + nota preprint una volta per voce.

## Formato di consegna
- **Email settimanale** (sempre una, mai zero): notifica con link a homepage se ci sono aggiornamenti, oppure reminder "Nessun aggiornamento questa settimana - DRA" se tutte le sezioni sono vuote. Oggetto sempre con suffisso "- DRA".
- **Note interne** (fetch falliti/energia a zero per 3 run consecutivi): email separata al comparto IT — mai un blocco automatico, solo segnalazione.
- **Sito web** (interno/privato, no login): una pagina per articolo, raggruppata per tema in cronologia. Homepage con box centrati dinamicamente, solo per temi con aggiornamenti nella settimana corrente. Badge "nuovo aggiornamento" (soglia ~2 giorni) calcolato **lato client**, non in generazione pagina. Stile visivo (colori, logo) rimandato — non bloccante, non implementare ora.
- Liste destinatari: file di config nel repo, nessuna sezione admin.

## Fuori scope per ora
- Server MCP pubblico: idea rimandata, non implementare. Va fatto solo dopo validazione della versione aziendale, in sessione separata.
- Scelta modello Gemini specifico (Flash-Lite/Flash/Pro): costo trascurabile in ogni caso, non bloccante.

## Convenzioni di lavoro per sessioni lunghe
- Committa a git ad ogni unità di lavoro completata (non a metà implementazione).
- Mantieni un file `claude-progress.txt` con log di cosa è stato fatto ad ogni sessione, per permettere a una sessione futura con contesto vuoto di ripartire senza rileggere tutto da capo.
- Se una sessione lavora su una parte (es. schema dati) e poi passa a un'altra non correlata (es. sito web), preferire una nuova sessione pulita piuttosto che accumulare contesto.
