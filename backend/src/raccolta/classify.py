"""Classificazione degli articoli nei 5 sotto-temi + filtro di rilevanza.

Riferimento: Notion sez. 16.3 (classificazione) e sez. 13/16.2 (filtro di
rilevanza tematica a monte per le fonti generaliste); DECISIONI.md §18.

Regole (tutto script, nessun giudizio del modello — coerente con ~80% script):
- Ogni articolo viene assegnato a ESATTAMENTE uno dei 5 temi, oppure a None
  ("null") per revisione manuale — mai a piu' di uno, mai a zero (16.3).
- L'assegnazione del tema segue la fonte di provenienza (mappa fonte->tema in
  config.yaml): e' una regola deterministica, non una valutazione del modello.
- Le fonti con `filtro_rilevanza` sono generaliste e aggregano anche contenuti
  fuori beat: Google Cloud Blog (database, sicurezza, strategia generica) e
  Tom's Hardware (offerte, gadget, gaming — usa il feed di sito perche' i feed
  per-tag sono stati dismessi). Questi vengono scartati a monte (-> None) se il
  testo non contiene alcuna parola chiave del beat
  (hardware/infrastruttura/capacita'), PRIMA della sintesi (16.2).
"""
from __future__ import annotations

import re

from ..schemas import Tema
from .fetch import Candidato

# Parole chiave che qualificano un contenuto come "in beat" (Infrastruttura &
# Hardware AI). Usate solo per il filtro di rilevanza delle fonti aggregatrici.
# Parametro di partenza, calibrabile.
#
# Il confronto e' per PREFISSO ANCORATO A INIZIO PAROLA (vedi `_compila`), non per
# sottostringa: cosi' "server" prende anche "servers" e "region" anche "regions",
# ma "chip" non scatta dentro "microchipped" a meta' parola.
PAROLE_BEAT: frozenset[str] = frozenset({
    # chip / silicio
    "gpu", "tpu", "chip", "silicon", "silicio", "semiconductor", "semicondutt",
    "accelerator", "acceleratore", "hbm", "nvlink", "wafer", "cuda",
    # data center / infrastruttura fisica
    "data center", "datacenter", "server", "rack", "cluster", "cooling",
    "raffreddamento", "infrastructure", "infrastruttura", "submarine cable",
    "cavo sottomarino", "region", "regione cloud", "availability zone",
    "interconnect", "fabric", "networking", "bandwidth", "banda", "tbps", "gbps",
    # capacita' / calcolo
    "capacity", "capacita", "capex", "supercomputer",
    # energia
    "power", "energy", "energia", "megawatt", "gigawatt", "grid",
})

# Parole che richiedono la corrispondenza ESATTA (parola intera), perche' sono
# prefisso o sottostringa di termini fuori beat molto comuni:
#   compute -> "computer"      mw -> "firmware"
#   nm      -> "nmap"          gw -> "gwei"
# Misurato sul feed Tom's Hardware: erano queste tre a far passare l'hack ESP32
# ("firmware"), il PC a batterie AA ("power") e Jurassic Park ("computer").
PAROLE_BEAT_ESATTE: frozenset[str] = frozenset({"compute", "mw", "gw", "nm"})

# Un'alternanza sola invece di N `in`: le parole normali ancorate a inizio parola
# (\b prima, nessun \b dopo -> i plurali passano), quelle esatte con \b da entrambi
# i lati. Ordinate per lunghezza decrescente cosi' l'alternanza preferisce il match
# piu' lungo. Compilata una volta all'import: `is_rilevante` gira su ogni candidato.
_RE_BEAT = re.compile(
    "|".join(
        [rf"\b{re.escape(k)}\b" for k in sorted(PAROLE_BEAT_ESATTE, key=len, reverse=True)]
        + [rf"\b{re.escape(k)}" for k in sorted(PAROLE_BEAT, key=len, reverse=True)]
    )
)

# Parole che, NEL TITOLO, marcano una storia di cybersicurezza: fuori beat anche
# se il testo contiene parole del beat. Caso reale (run 2026-07-22): l'incidente
# "OpenAI models break out ... hacked HuggingFace's production servers" passava
# per "servers" e finiva in chip, ma e' cronaca di sicurezza, non hardware.
#
# SOLO IL TITOLO, per scelta: e' la testata a dire di cosa parla la storia. Nel
# corpo queste parole compaiono anche in articoli in beat (retro-test sui 42
# articoli passati delle fonti filtrate: sull'intero testo l'esclusione ne
# avrebbe scartati 6, tra cui il roundup "What's new with Google Cloud"; sul
# solo titolo 1 — esattamente il falso positivo). Vale solo per le fonti con
# `filtro_rilevanza`: una fonte curata resta libera di titolare come vuole.
PAROLE_FUORI_BEAT_TITOLO: frozenset[str] = frozenset({
    "hack", "hacked", "hacker", "cybersecurity", "breach", "malware",
    "ransomware", "phishing",
})

_RE_FUORI_BEAT_TITOLO = re.compile(
    "|".join(rf"\b{re.escape(k)}" for k in sorted(PAROLE_FUORI_BEAT_TITOLO, key=len, reverse=True))
)


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
    if _RE_FUORI_BEAT_TITOLO.search(candidato.titolo.lower()):
        return False
    return _RE_BEAT.search(_testo(candidato)) is not None


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
