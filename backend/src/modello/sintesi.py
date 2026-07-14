"""Sintesi degli articoli e assemblaggio del Digest.

Il modello produce solo i campi testuali (`sintesi`, `perche_conta`, `note`);
i metadati (titolo, fonte, link, data) restano quelli reali del candidato
(grounding: nessun URL inventato). L'assemblaggio nelle 5 sezioni fisse e' codice.

Il generatore e' iniettabile: `genera(prompt) -> dict` (Gemini in produzione, un
mock nei test). Come fallback interno, `genera=None` produce una sintesi
deterministica dal titolo/estratto senza modello (usato solo dai test).
"""
from __future__ import annotations

from typing import Callable

from .prompts import NOTA_PREPRINT, e_arxiv, prompt_sintesi, prompt_titolo_gruppo
from ..schemas import (
    TEMI_ORDINE,
    Articolo,
    Digest,
    Fonte,
    GruppoGiorno,
    NotaInterna,
    Sezione,
    Stato,
    Tema,
)
from ..raccolta.fetch import Candidato

Generatore = Callable[[str], dict]


def _sintesi_fallback(c: Candidato) -> dict:
    """Sintesi deterministica senza modello (fallback interno, usato dai test)."""
    base = c.estratto.strip() or c.titolo.strip()
    return {
        "sintesi": base,
        "perche_conta": f"Rilevante per il tema {c.tema}.",
        "note": "",
    }


def _con_nota_arxiv(c: Candidato, note: str | None) -> str | None:
    if not e_arxiv(c):
        return note or None
    if note:
        return f"{note} {NOTA_PREPRINT}"
    return NOTA_PREPRINT


def sintetizza_candidato(c: Candidato, genera: Generatore | None) -> Articolo:
    """Sintetizza un singolo candidato in un Articolo (metadati reali del candidato)."""
    dati = _sintesi_fallback(c) if genera is None else genera(prompt_sintesi(c))
    sintesi = str(dati.get("sintesi", "")).strip() or c.titolo.strip()
    perche = str(dati.get("perche_conta", "")).strip()
    note = _con_nota_arxiv(c, (dati.get("note") or "").strip() or None)
    return Articolo(
        titolo=c.titolo,
        fonti=[Fonte(nome=c.fonte, link=c.url)],  # grounding: link reale del candidato
        data=c.data,
        sintesi=sintesi,
        perche_conta=perche,
        note=note,
    )


def _raggruppa_per_giorno(articoli: list[Articolo]) -> list[tuple[str, list[Articolo]]]:
    """Raggruppa gli articoli per `data` (ISO), preservando l'ordine di apparizione
    sia dei giorni sia degli articoli dentro ciascun giorno."""
    per_giorno: dict[str, list[Articolo]] = {}
    for a in articoli:
        per_giorno.setdefault(a.data, []).append(a)
    return list(per_giorno.items())


def sintetizza_titolo_gruppo(
    tema: Tema, articoli: list[Articolo], genera: Generatore | None
) -> str:
    """Titolo riassuntivo per un gruppo di articoli dello stesso giorno.

    Con un solo articolo il titolo del gruppo È quello dell'articolo (nessuna
    chiamata al modello). Con più articoli si chiede al modello una riga di
    sommario; in mancanza di modello (test/demo) o di risposta utile si ripiega
    sul titolo del primo articolo.
    """
    if len(articoli) == 1 or genera is None:
        return articoli[0].titolo
    voci = [(a.titolo, a.sintesi) for a in articoli]
    label = tema.value.replace("_", " ")
    try:
        dati = genera(prompt_titolo_gruppo(label, voci))
    except Exception:  # noqa: BLE001 - un titolo mancante non deve fermare la run
        return articoli[0].titolo
    return str(dati.get("titolo", "")).strip() or articoli[0].titolo


def assembla_digest(
    gruppi: dict[Tema, list[Candidato]],
    genera: Generatore | None,
    data_generazione: str,
    note_interne: list[NotaInterna] | None = None,
) -> Digest:
    """Costruisce il Digest con le 5 sezioni fisse a partire dai candidati per tema.

    Le sezioni senza candidati risultano `nessun_aggiornamento` (il modello NON
    viene invocato per esse: nessun costo, nessun testo generato). Per le sezioni
    con aggiornamenti, gli articoli dello stesso giorno vengono anche riassunti in
    un `GruppoGiorno` (titolo del gruppo) per la presentazione sul sito.
    """
    sezioni: list[Sezione] = []
    for tema in TEMI_ORDINE:
        candidati = gruppi.get(tema, [])
        if not candidati:
            sezioni.append(Sezione(tema=tema, stato=Stato.nessun_aggiornamento, articoli=[]))
            continue
        articoli = [sintetizza_candidato(c, genera) for c in candidati]
        gruppi_giorno = [
            GruppoGiorno(data=data, titolo=sintetizza_titolo_gruppo(tema, arts, genera))
            for data, arts in _raggruppa_per_giorno(articoli)
        ]
        sezioni.append(Sezione(
            tema=tema, stato=Stato.con_aggiornamenti,
            articoli=articoli, gruppi=gruppi_giorno,
        ))
    return Digest(
        data_generazione=data_generazione,
        sezioni=sezioni,
        note_interne=note_interne or [],
    )
