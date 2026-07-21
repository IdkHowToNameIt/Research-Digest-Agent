"""Sintesi degli articoli e assemblaggio del Digest.

Il modello produce solo i campi testuali (`sintesi`, `perche_conta`, `note`);
i metadati (titolo, fonte, link, data) restano quelli reali del candidato
(grounding: nessun URL inventato). L'assemblaggio nelle 5 sezioni fisse e' codice.

Il generatore e' iniettabile: `genera(prompt) -> dict` (Groq in produzione, un
mock nei test). Come fallback interno, `genera=None` produce una sintesi
deterministica dal titolo/estratto senza modello (usato solo dai test).
"""
from __future__ import annotations

import re
from typing import Callable

from .prompts import (
    NOTA_PREPRINT,
    e_arxiv,
    prompt_etichette_gruppo,
    prompt_sintesi,
    prompt_titolo_gruppo,
)
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
        "titolo": c.titolo.strip(),   # senza modello non si traduce: titolo reale
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


def _con_nota_testate(c: Candidato, note: str | None) -> str | None:
    """Aggiunge "ripreso da N testate" alle notizie accorpate da un aggregatore.

    Convenzione 14.7, prevista in `schemas.py` e rimasta senza codice che la
    producesse finche' non e' esistito il raggruppamento per storia (sez. 24).
    Il numero e' un'informazione editoriale vera: dice al lettore che la notizia
    ha avuto eco, cosa che il solo conteggio degli articoli nascondeva.
    """
    if c.n_testate <= 1:
        return note or None
    nota = f"(ripreso da {c.n_testate} testate)"
    return f"{note} {nota}" if note else nota


def sintetizza_candidato(c: Candidato, genera: Generatore | None) -> Articolo:
    """Sintetizza un singolo candidato in un Articolo (metadati reali del candidato)."""
    dati = _sintesi_fallback(c) if genera is None else genera(prompt_sintesi(c))
    sintesi = str(dati.get("sintesi", "")).strip() or c.titolo.strip()
    perche = str(dati.get("perche_conta", "")).strip()
    note = _con_nota_arxiv(c, (dati.get("note") or "").strip() or None)
    note = _con_nota_testate(c, note)
    # titolo mostrato = riscrittura italiana del modello, con fallback al titolo reale
    # (grounding: il LINK resta sempre quello reale del candidato, mai del modello).
    titolo = str(dati.get("titolo", "")).strip() or c.titolo.strip()
    return Articolo(
        titolo=titolo,
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


# Il prompt del titolo-gruppo chiede di non forzare un legame che non c'e'. Se le
# notizie del giorno sono fuori tema il modello obbedisce alla lettera e risponde
# "Nessuna notizia disponibile su data center" — che finiva pubblicato come titolo
# del gruppo (run del 2026-07-21, tema data_center del 15/07, gruppo con 2 voci).
# Il ripiego esisteva gia' ma scattava solo sul titolo VUOTO: una frase di rifiuto
# e' non-vuota e passava indisturbata.
_NON_TITOLI = re.compile(
    r"nessun[ao]\b|non (?:è|e'|e) (?:possibile|disponibile)|non ci sono\b"
    r"|non sono (?:presenti|disponibili)|non risulta|mi dispiace|come assistente"
    r"|non posso\b|impossibile (?:determinare|trovare)",
    re.IGNORECASE,
)


def _e_non_titolo(titolo: str) -> bool:
    """True se il modello ha risposto con un rifiuto invece che con un titolo.

    Deliberatamente conservativa: cerca formule di rifiuto, non giudica la
    qualita' del titolo. Un falso positivo costa poco (si ripiega sul titolo del
    primo articolo, che e' sempre un titolo reale e in tema), un falso negativo
    pubblica una frase di scuse in cima al digest.
    """
    return _NON_TITOLI.search(titolo) is not None


# Quante etichette si accostano al massimo: oltre due la card diventa una riga
# lunghissima e illeggibile, quindi il resto si riassume in "e altro".
MAX_FRAMMENTI = 2
# Tetto di sicurezza sulle etichette del modello: il prompt ne chiede 2-5 parole,
# questo lo rende vero anche quando non obbedisce.
MAX_PAROLE_ETICHETTA = 5
SEPARATORE = "; "
CODA_ALTRO = " e altro"

# Parole di servizio su cui vale la pena troncare un titolo reale: introducono una
# subordinata o un complemento accessorio, e quello che segue di solito non serve a
# capire l'argomento. NON ci sono le preposizioni articolate del genitivo
# (della/dei/nel...): quelle legano il gruppo nominale, e tagliarci sopra
# spezzerebbe "Esplorazione della rappresentazione" in "Esplorazione".
_TAGLIO = re.compile(
    r"\s+(?:per|con|che|dopo|mentre|come|dove|quando|se|sulla|sul|sui|sulle|"
    r"grazie|verso|contro|senza|entro|oltre)\s+",
    re.IGNORECASE,
)
_MIN_PAROLE_TAGLIO = 3

# Parole che non possono chiudere un frammento: articoli, preposizioni, congiunzioni.
_CODA_SOSPESA = re.compile(
    r"(?:il|lo|la|i|gli|le|un|uno|una|l|dell|della|dello|degli|delle|dei|del|"
    r"di|da|in|su|tra|fra|e|ed|a|ad|al|allo|alla|ai|agli|alle|nel|nella|nei|"
    r"negli|nelle|con|per|come|che)['’]?",
    re.IGNORECASE,
)


def _frammento_da_titolo(titolo: str, max_parole: int = 5) -> str:
    """Ripiego deterministico: accorcia un titolo reale a un frammento breve.

    Si taglia sulla prima parola di servizio che lasci dietro di se' almeno
    `_MIN_PAROLE_TAGLIO` parole — non sulla prima in assoluto, altrimenti un
    titolo che comincia con "X per ..." si ridurrebbe alla sola "X" — e comunque
    a `max_parole`. Grezzo rispetto a un'etichetta scritta dal modello, ma non
    inventa nulla e non costa quota.
    """
    testo = titolo.strip().rstrip(".")
    for taglio in _TAGLIO.finditer(testo):
        if len(testo[: taglio.start()].split()) >= _MIN_PAROLE_TAGLIO:
            testo = testo[: taglio.start()]
            break
    parole = testo.split()[:max_parole]
    # Il taglio a max_parole cade spesso su un articolo o una preposizione
    # ("...costruisce la", "...gerarchica degli"): lasciarlo li' fa sembrare la
    # riga troncata a meta'. Si arretra finche' l'ultima parola non regge da sola.
    while len(parole) > 1 and _CODA_SOSPESA.fullmatch(parole[-1]):
        parole.pop()
    return " ".join(parole).rstrip(",;:")


def _minuscola_iniziale(frammento: str) -> str:
    """Abbassa l'iniziale, ma NON di sigle e nomi propri.

    "Progressi" -> "progressi", mentre "TSMC" e "GeForce" restano intatti: si
    riconoscono dal fatto che hanno altre maiuscole dopo la prima ("tSMC" era il
    risultato della versione ingenua, preso da un test).
    """
    prima = frammento.split(" ", 1)[0]
    if prima[1:] != prima[1:].lower():
        return frammento
    return frammento[0].lower() + frammento[1:]


def _componi(frammenti: list[str], totale: int) -> str:
    """Accosta i frammenti: al massimo MAX_FRAMMENTI, poi "e altro".

    Il primo frammento tiene la maiuscola, gli altri vanno in minuscolo perche'
    il risultato si legga come una riga sola e non come titoli incollati.
    """
    scelti = [f for f in frammenti if f][:MAX_FRAMMENTI]
    if not scelti:
        return ""
    testa = scelti[0][0].upper() + scelti[0][1:]
    coda = [_minuscola_iniziale(f) for f in scelti[1:]]
    riga = SEPARATORE.join([testa, *coda])
    return riga + CODA_ALTRO if totale > len(scelti) else riga


def _titolo_composto(
    tema: Tema, articoli: list[Articolo], genera: Generatore
) -> str:
    """Titolo per un gruppo SENZA filo conduttore: etichette brevi accostate.

    Chiedere un riassunto unico a notizie scollegate e' una domanda mal posta e
    il modello risponde con un rifiuto. Qui gli si chiede invece un'etichetta per
    ciascuna notizia; se anche questo fallisce si ripiega sui titoli reali
    accorciati dal codice, cosi' il caso non resta mai scoperto.
    """
    voci = [(a.titolo, a.sintesi) for a in articoli]
    label = tema.value.replace("_", " ")
    etichette: list[str] = []
    try:
        dati = genera(prompt_etichette_gruppo(label, voci))
        grezze = dati.get("etichette") or []
        if isinstance(grezze, list):
            etichette = [
                # Il prompt chiede 2-5 parole ma non puo' imporlo: se il modello
                # restituisce una frase intera (o rimanda il titolo cosi' com'e')
                # la riga composta diventa illeggibile sulla card. Si accorcia con
                # lo stesso taglio del ripiego deterministico.
                _frammento_da_titolo(str(e).strip(), max_parole=MAX_PAROLE_ETICHETTA)
                for e in grezze
                if str(e).strip() and not _e_non_titolo(str(e))
            ]
    except Exception:  # noqa: BLE001 - il ripiego deterministico copre comunque
        etichette = []
    if len(etichette) < min(len(articoli), MAX_FRAMMENTI):
        etichette = [_frammento_da_titolo(a.titolo) for a in articoli]
    return _componi(etichette, len(articoli))


def sintetizza_titolo_gruppo(
    tema: Tema, articoli: list[Articolo], genera: Generatore | None
) -> str:
    """Titolo riassuntivo per un gruppo di articoli dello stesso giorno.

    Con un solo articolo il titolo del gruppo È quello dell'articolo (nessuna
    chiamata al modello). Con più articoli si chiede al modello una riga di
    sommario.

    Se il modello si rifiuta — perché le notizie non hanno davvero un filo
    conduttore — non si ripiega sul titolo del PRIMO articolo, che nasconderebbe
    gli altri: si compone un titolo accostando un'etichetta breve per notizia
    (§23.4). Senza modello (test/demo) resta il titolo del primo articolo.
    """
    if len(articoli) == 1 or genera is None:
        return articoli[0].titolo
    voci = [(a.titolo, a.sintesi) for a in articoli]
    label = tema.value.replace("_", " ")
    try:
        dati = genera(prompt_titolo_gruppo(label, voci))
    except Exception:  # noqa: BLE001 - un titolo mancante non deve fermare la run
        return articoli[0].titolo
    titolo = str(dati.get("titolo", "")).strip()
    if not titolo or _e_non_titolo(titolo):
        return _titolo_composto(tema, articoli, genera) or articoli[0].titolo
    return titolo


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
