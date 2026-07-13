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

from .prompts import NOTA_PREPRINT, e_arxiv, prompt_sintesi
from ..schemas import (
    TEMI_ORDINE,
    Articolo,
    Digest,
    Fonte,
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


def assembla_digest(
    gruppi: dict[Tema, list[Candidato]],
    genera: Generatore | None,
    data_generazione: str,
    note_interne: list[NotaInterna] | None = None,
) -> Digest:
    """Costruisce il Digest con le 5 sezioni fisse a partire dai candidati per tema.

    Le sezioni senza candidati risultano `nessun_aggiornamento` (il modello NON
    viene invocato per esse: nessun costo, nessun testo generato).
    """
    sezioni: list[Sezione] = []
    for tema in TEMI_ORDINE:
        candidati = gruppi.get(tema, [])
        if not candidati:
            sezioni.append(Sezione(tema=tema, stato=Stato.nessun_aggiornamento, articoli=[]))
        else:
            articoli = [sintetizza_candidato(c, genera) for c in candidati]
            sezioni.append(Sezione(tema=tema, stato=Stato.con_aggiornamenti, articoli=articoli))
    return Digest(
        data_generazione=data_generazione,
        sezioni=sezioni,
        note_interne=note_interne or [],
    )
