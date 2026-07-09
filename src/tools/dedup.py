"""Deduplicazione: esatta (hash) + fuzzy con rilevamento novità (sez. 16.4).

Due livelli:
1. Hash esatto su (titolo normalizzato + URL) contro tutto lo storico: se coincide
   e' un duplicato esatto, scartato.
2. Overlap fuzzy nella finestra di 4-6 settimane. Per l'articolo archiviato piu'
   simile si calcola l'overlap di parole/entita' (indice di Jaccard):
   - overlap < soglia  -> articolo distinto (nessun controllo di segnali);
   - overlap >= soglia -> si valutano 3 segnali di novita' indipendenti:
       * numerico: l'insieme dei numeri (con unita': %, $, GW, MW, nm, miliardi...)
         del nuovo articolo differisce da quello del simile;
       * temporale: il nuovo articolo cita una data piu' recente (nel testo,
         non la data di pubblicazione);
       * entita': il nuovo articolo nomina un'entita' assente nel simile.
     almeno un segnale presente -> aggiornamento legittimo (incluso);
     nessun segnale            -> duplicato (scartato).

Soglia (0,7) ed elenco entita' note sono parametri di partenza CALIBRABILI
(sez. 16.4), non valori fissi definitivi.

Tutte le funzioni di analisi sono pure e testabili senza I/O; `deduplica()`
integra il confronto con lo storico (SeenStore).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from ..state import SeenStore
from .fetch import Candidato

# --- entita' note del beat (parametro di partenza, calibrabile) -------------
ENTITA_NOTE: frozenset[str] = frozenset({
    # aziende / attori
    "nvidia", "amd", "intel", "tsmc", "asml", "samsung", "sk hynix", "micron",
    "broadcom", "arm", "qualcomm", "apple", "google", "alphabet", "microsoft",
    "azure", "aws", "amazon", "meta", "openai", "anthropic", "oracle", "supermicro",
    # prodotti / architetture
    "blackwell", "hopper", "gb200", "h100", "h200", "mi300", "gemini", "cuda",
    # paesi rilevanti (export/supply chain)
    "cina", "china", "taiwan", "stati uniti", "usa", "united states", "paesi bassi",
    "netherlands", "olanda", "giappone", "japan", "corea", "korea", "germania",
})

# stopword essenziali (it + en) per ridurre il rumore nell'overlap.
_STOPWORD: frozenset[str] = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "has",
    "have", "not", "but", "will", "una", "uno", "che", "per", "con", "del",
    "della", "dei", "delle", "come", "sono", "gli", "the", "nel", "nella",
    "alla", "allo", "dai", "dal", "più", "piu", "non", "una", "suo", "sua",
    "loro", "anche", "questa", "questo", "essere", "stato", "dopo", "prima",
})


def _strip_accenti(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def normalizza_titolo(titolo: str) -> str:
    """Minuscolo, senza punteggiatura, spazi normalizzati (per l'hash esatto)."""
    t = _strip_accenti(titolo.lower())
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def hash_esatto(titolo: str, url: str) -> str:
    """Hash su (titolo normalizzato + URL normalizzato)."""
    base = f"{normalizza_titolo(titolo)}|{url.strip().lower().rstrip('/')}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def parole_significative(testo: str) -> set[str]:
    """Insieme di parole >=3 lettere, senza accenti/stopword (per il Jaccard)."""
    t = _strip_accenti(testo.lower())
    token = re.findall(r"[a-z0-9]+", t)
    return {w for w in token if len(w) >= 3 and w not in _STOPWORD}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    unione = len(a | b)
    return inter / unione if unione else 0.0


# --- segnale numerico -------------------------------------------------------
_UNITA = r"%|tbps|gbps|gwh|mwh|kwh|gw|mw|kw|nm|miliard\w*|milion\w*|billion|million|bn|mld|watt"
_NUM_RE = re.compile(
    r"(?P<sym>[$€])?\s?(?P<num>\d[\d.,]*)\s?(?P<unit>" + _UNITA + r")?", re.I
)


def estrai_numeri(testo: str) -> set[str]:
    """Insieme di token numerici rilevanti (con valuta o unita').

    I numeri "nudi" (senza simbolo di valuta ne' unita', es. anni) sono ignorati:
    il segnale numerico riguarda cifre come capex, energia, banda, nm (sez. 16.4).
    """
    numeri: set[str] = set()
    for m in _NUM_RE.finditer(testo):
        sym, num, unit = m.group("sym"), m.group("num"), m.group("unit")
        if not sym and not unit:
            continue
        cifre = num.replace(".", "").replace(",", "")
        unita = (unit or "").lower()
        # normalizza classi di scala equivalenti
        if unita.startswith("miliard") or unita in {"bn", "mld", "billion"}:
            unita = "mld"
        elif unita.startswith("milion") or unita == "million":
            unita = "mln"
        numeri.add(f"{sym or ''}{cifre}{unita}")
    return numeri


def segnale_numerico(testo_nuovo: str, testo_vecchio: str) -> bool:
    return bool(estrai_numeri(testo_nuovo) - estrai_numeri(testo_vecchio))


# --- segnale temporale ------------------------------------------------------
_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}
_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_MESE_ANNO_RE = re.compile(
    r"\b(\d{1,2}\s+)?(" + "|".join(_MESI) + r")\s+(20\d{2})\b", re.I
)
_ANNO_RE = re.compile(r"\b(20\d{2})\b")


def _date_citate(testo: str) -> list[tuple[int, int, int]]:
    date: list[tuple[int, int, int]] = []
    for y, m, d in _ISO_RE.findall(testo):
        date.append((int(y), int(m), int(d)))
    for _g, mese, anno in _MESE_ANNO_RE.findall(testo):
        date.append((int(anno), _MESI[mese.lower()], 1))
    for anno in _ANNO_RE.findall(testo):
        date.append((int(anno), 1, 1))
    return date


def segnale_temporale(testo_nuovo: str, testo_vecchio: str) -> bool:
    """True se il nuovo articolo cita una data piu' recente del simile."""
    nuove = _date_citate(testo_nuovo)
    vecchie = _date_citate(testo_vecchio)
    if not nuove:
        return False
    if not vecchie:
        return True
    return max(nuove) > max(vecchie)


# --- segnale entita' --------------------------------------------------------
_CAP_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*)\b")


def estrai_entita(testo: str, entita_note: frozenset[str] = ENTITA_NOTE) -> set[str]:
    """Entita' = match di entita' note + euristica su sequenze capitalizzate."""
    ent: set[str] = set()
    testo_low = testo.lower()
    for nota in entita_note:
        if nota in testo_low:
            ent.add(nota)
    for m in _CAP_RE.findall(testo):
        parola = m.strip().lower()
        if len(parola) >= 3:
            ent.add(parola)
    return ent


def segnale_entita(
    testo_nuovo: str, testo_vecchio: str, entita_note: frozenset[str] = ENTITA_NOTE
) -> bool:
    return bool(
        estrai_entita(testo_nuovo, entita_note) - estrai_entita(testo_vecchio, entita_note)
    )


# --- regola di decisione ----------------------------------------------------
@dataclass
class EsitoConfronto:
    decisione: str            # "distinto" | "aggiornamento" | "duplicato"
    overlap: float
    segnali: list[str]


def valuta_coppia(
    testo_nuovo: str,
    testo_vecchio: str,
    soglia: float = 0.7,
    entita_note: frozenset[str] = ENTITA_NOTE,
) -> EsitoConfronto:
    """Applica la regola di sez. 16.4 tra un nuovo articolo e uno simile."""
    overlap = jaccard(parole_significative(testo_nuovo), parole_significative(testo_vecchio))
    if overlap < soglia:
        return EsitoConfronto("distinto", overlap, [])
    segnali: list[str] = []
    if segnale_numerico(testo_nuovo, testo_vecchio):
        segnali.append("numerico")
    if segnale_temporale(testo_nuovo, testo_vecchio):
        segnali.append("temporale")
    if segnale_entita(testo_nuovo, testo_vecchio, entita_note):
        segnali.append("entita")
    decisione = "aggiornamento" if segnali else "duplicato"
    return EsitoConfronto(decisione, overlap, segnali)


# --- integrazione con lo storico -------------------------------------------
def _testo_candidato(c: Candidato) -> str:
    # confine di frase tra titolo ed estratto: evita che l'ultima parola del
    # titolo e la prima dell'estratto vengano lette come un'unica entita'
    # capitalizzata (falso segnale entita').
    titolo = c.titolo.strip().rstrip(".")
    estratto = c.estratto.strip()
    return f"{titolo}. {estratto}".strip() if estratto else titolo


@dataclass
class EsitoCandidato:
    candidato: Candidato
    decisione: str            # "nuovo" | "duplicato_esatto" | "duplicato" | "aggiornamento"
    overlap: float = 0.0
    segnali: list[str] | None = None


def deduplica(
    candidati: list[Candidato],
    store: SeenStore,
    *,
    soglia: float = 0.7,
    finestra_settimane: int = 6,
    entita_note: frozenset[str] = ENTITA_NOTE,
    ora: datetime | None = None,
) -> tuple[list[Candidato], list[EsitoCandidato]]:
    """Filtra i candidati contro lo storico e all'interno dello stesso run.

    Ritorna (tenuti, esiti). I candidati "aggiornamento" sono inclusi (novita'
    legittima nonostante l'alto overlap). NON persiste nulla: la registrazione
    nello storico avviene a valle, solo per gli articoli effettivamente pubblicati.
    """
    ora = ora or datetime.now(timezone.utc)
    recenti = store.articoli_recenti(ora, finestra_settimane)
    tenuti: list[Candidato] = []
    esiti: list[EsitoCandidato] = []
    hash_run: set[str] = set()

    for c in candidati:
        if not c.url:
            continue
        h = hash_esatto(c.titolo, c.url)
        if h in hash_run or store.hash_esiste(h):
            esiti.append(EsitoCandidato(c, "duplicato_esatto"))
            continue

        testo_nuovo = _testo_candidato(c)
        migliore: EsitoConfronto | None = None
        for art in recenti:
            esito = valuta_coppia(testo_nuovo, art.testo, soglia, entita_note)
            if migliore is None or esito.overlap > migliore.overlap:
                migliore = esito

        if migliore is not None and migliore.overlap >= soglia and migliore.decisione == "duplicato":
            esiti.append(EsitoCandidato(c, "duplicato", migliore.overlap, []))
            continue

        # nuovo (nessun simile sopra soglia) oppure aggiornamento legittimo
        hash_run.add(h)
        tenuti.append(c)
        if migliore is not None and migliore.overlap >= soglia:
            esiti.append(EsitoCandidato(c, "aggiornamento", migliore.overlap, migliore.segnali))
        else:
            esiti.append(EsitoCandidato(c, "nuovo", migliore.overlap if migliore else 0.0, []))

    return tenuti, esiti


def registra_pubblicati(candidati: list[Candidato], store: SeenStore) -> None:
    """Archivia nello storico gli articoli effettivamente pubblicati (per i run
    futuri): hash, url, titolo normalizzato e testo per il confronto fuzzy."""
    for c in candidati:
        store.registra_articolo(
            hash_esatto(c.titolo, c.url),
            c.url,
            normalizza_titolo(c.titolo),
            _testo_candidato(c),
        )


# --- compatibilita' con lo starter (dedup esatto per URL nello stesso run) --
def filtra_nuove(candidati: list[Candidato], store: SeenStore) -> list[Candidato]:
    visti_in_run: set[str] = set()
    nuove: list[Candidato] = []
    for c in candidati:
        if not c.url or c.url in visti_in_run:
            continue
        if store.is_seen(c.url):
            continue
        visti_in_run.add(c.url)
        nuove.append(c)
    return nuove
