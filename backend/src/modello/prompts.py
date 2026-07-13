"""Criteri editoriali e costruzione del prompt di sintesi (sez. 14).

Il modello (Gemini) interviene SOLO sulla sintesi testuale del singolo articolo
(campi `sintesi`, `perche_conta`, eventuale `note`): non sceglie le fonti, non
inventa URL, non produce lo schema del digest (quello e' assemblato da codice).
Metadati (titolo, fonte, link, data) restano quelli reali del candidato.
"""
from __future__ import annotations

from ..schemas import Tema
from ..raccolta.fetch import Candidato

# Formula di apertura fissa per gli articoli arXiv (sez. 14.8).
APERTURA_ARXIV = "I risultati preliminari di uno studio indicano che"
NOTA_PREPRINT = "(preprint, non ancora sottoposto a peer review)"


def e_arxiv(c: Candidato) -> bool:
    """True se il candidato proviene da arXiv (fonte energia unica)."""
    return c.tema == Tema.energia.value or "arxiv" in c.fonte.lower()


CRITERI_EDITORIALI = f"""Sei l'editor di un digest di ricerca settimanale sul beat
"Infrastruttura & Hardware AI" (chip, data center, energia, supply chain, cloud capacity).
Target: CTO, investitori infrastrutturali, lettori che vogliono i vincoli reali dietro l'AI.

REGOLE NON NEGOZIABILI (grounding):
- Usa SOLO le informazioni contenute nel titolo e nell'estratto forniti. NON inventare
  fatti, numeri, nomi, citazioni o dettagli non presenti nella fonte.
- Dati quantitativi (capex, energia, capacita', banda): riportali SOLO se citati
  testualmente nella fonte, MAI riformulati, interpretati o arrotondati. Nel dubbio,
  ometti il numero.
- Se l'estratto e' assente (solo titolo), scrivi una sintesi minima basata unicamente
  sul titolo, senza aggiungere dettagli non presenti.

STILE (sez. 14):
- Lingua: italiano. Tono: divulgativo-preciso + business/investitori, con un minimo di
  precisione tecnica (non perdere il lettore CTO).
- Lunghezza sintesi: 3-5 frasi; estendibile a 6-8 solo se l'estratto contiene davvero
  piu' informazione fattuale verificabile (numeri, entita', dati concreti), mai per
  enfatizzare l'importanza del tema.
- Filtro marketing moderato sulle fonti corporate (Azure/AWS/Google Cloud): rimuovi il
  linguaggio promozionale esplicito ma conserva il contesto economico rilevante
  (cifre di investimento, capacita' annunciate).
- "perche_conta": una frase sul perche' e' rilevante per il beat/gli investitori.
  Sempre presente, mai vuota.

OUTPUT: rispondi con un oggetto JSON con esattamente queste chiavi:
  {{"sintesi": "...", "perche_conta": "...", "note": "" }}
"note" e' opzionale (stringa vuota se non serve)."""


def prompt_sintesi(c: Candidato) -> str:
    """Costruisce il prompt per la sintesi di un singolo candidato."""
    righe = [CRITERI_EDITORIALI, "", "--- ARTICOLO DA SINTETIZZARE ---",
             f"Titolo: {c.titolo}",
             f"Fonte: {c.fonte}",
             f"Estratto: {c.estratto or '(nessun estratto disponibile: usa solo il titolo)'}"]
    if e_arxiv(c):
        righe += [
            "",
            "NOTA FONTE arXiv (preprint accademico): apri la sintesi con la formula "
            f"\"{APERTURA_ARXIV}...\" (o variante equivalente), mai con linguaggio da "
            "cronaca (\"e' stato annunciato che...\"). Non aggiungere tu la dicitura "
            "preprint: la inserisce il codice.",
        ]
    return "\n".join(righe)
