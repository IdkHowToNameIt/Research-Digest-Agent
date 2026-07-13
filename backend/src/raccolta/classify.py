"""Classificazione degli articoli nei 5 sotto-temi + filtro di rilevanza.

Riferimento: Notion sez. 16.3 (classificazione) e sez. 13/16.2 (filtro di
rilevanza tematica a monte per Google Cloud Blog).

Regole (tutto script, nessun giudizio del modello — coerente con ~80% script):
- Ogni articolo viene assegnato a ESATTAMENTE uno dei 5 temi, oppure a None
  ("null") per revisione manuale — mai a piu' di uno, mai a zero (16.3).
- L'assegnazione del tema segue la fonte di provenienza (mappa fonte->tema in
  config.yaml): e' una regola deterministica, non una valutazione del modello.
- Le fonti con `filtro_rilevanza` (Google Cloud Blog) aggregano anche contenuti
  fuori beat (database, sicurezza, strategia generica): questi vengono scartati
  a monte (-> None) se il testo non contiene alcuna parola chiave del beat
  (hardware/infrastruttura/capacita'), PRIMA della sintesi (16.2).
"""
from __future__ import annotations

from ..schemas import Tema
from .fetch import Candidato

# Parole chiave che qualificano un contenuto come "in beat" (Infrastruttura &
# Hardware AI). Usate solo per il filtro di rilevanza delle fonti aggregatrici.
# Parametro di partenza, calibrabile.
PAROLE_BEAT: frozenset[str] = frozenset({
    # chip / silicio
    "gpu", "tpu", "chip", "silicon", "silicio", "semiconductor", "semicondutt",
    "accelerator", "acceleratore", "hbm", "nvlink", "wafer", "nm ", "cuda",
    # data center / infrastruttura fisica
    "data center", "datacenter", "server", "rack", "cluster", "cooling",
    "raffreddamento", "infrastructure", "infrastruttura", "submarine cable",
    "cavo sottomarino", "region", "regione cloud", "availability zone",
    "interconnect", "fabric", "networking", "bandwidth", "banda", "tbps", "gbps",
    # capacita' / calcolo
    "compute", "capacity", "capacita", "capex", "supercomputer",
    # energia
    "power", "energy", "energia", "megawatt", "gigawatt", "mw", "gw", "grid",
})


def _testo(candidato: Candidato) -> str:
    return f"{candidato.titolo} {candidato.estratto}".lower()


def is_rilevante(candidato: Candidato) -> bool:
    """True se il candidato e' in beat.

    Per le fonti senza `filtro_rilevanza` e' sempre True (la selezione della
    fonte stessa garantisce l'attinenza). Per le fonti con `filtro_rilevanza`,
    richiede almeno una parola chiave del beat nel titolo o nell'estratto.
    """
    if not candidato.filtro_rilevanza:
        return True
    testo = _testo(candidato)
    return any(kw in testo for kw in PAROLE_BEAT)


def classifica(candidato: Candidato) -> Tema | None:
    """Assegna il candidato a un tema, oppure None (revisione manuale).

    Ritorna None se:
    - il candidato non supera il filtro di rilevanza (fonte aggregatrice fuori beat);
    - il tema di provenienza non e' un valore valido (difensivo).
    """
    if not is_rilevante(candidato):
        return None
    try:
        return Tema(candidato.tema)
    except ValueError:
        return None


def raggruppa_per_tema(
    candidati: list[Candidato],
) -> tuple[dict[Tema, list[Candidato]], list[Candidato]]:
    """Raggruppa i candidati per tema. Ritorna (gruppi, scartati).

    `gruppi` ha sempre tutte e 5 le chiavi (anche liste vuote), coerente con le
    5 sezioni fisse. `scartati` contiene i candidati classificati None.
    """
    gruppi: dict[Tema, list[Candidato]] = {t: [] for t in Tema}
    scartati: list[Candidato] = []
    for c in candidati:
        tema = classifica(c)
        if tema is None:
            scartati.append(c)
        else:
            gruppi[tema].append(c)
    return gruppi, scartati
