"""Generazione delle note interne (sez. 16.1 fetch, 16.3 energia).

Segnalazioni operative per il team (canale: email separata al comparto IT,
sez. 17.2), generate SOLO da script, mai dal modello, mai esposte nel digest
pubblico. Regole:
- una fonte in `fetch_failed` per >= 3 run consecutivi -> nota di verifica manuale;
- la sezione energia con 0 articoli per >= 3 run consecutivi -> nota di controllo
  manuale (fonte unica arXiv).
In nessun caso una nota comporta un blocco automatico della fonte o della sezione:
la sezione continua a essere generata regolarmente e il digest mostra comunque lo
stato standard "nessun_aggiornamento" per quella settimana (sez. 16.3).
"""
from __future__ import annotations

from ..schemas import NotaInterna, Tema, TipoNotaInterna
from ..state import SeenStore
from ..raccolta.fetch import STATO_FETCH_FAILED, EsitoFonte

# Numero di run consecutivi che fa scattare una nota (parametro, non fisso).
SOGLIA_RUN_CONSECUTIVI = 3

_CHIAVE_FETCH = "fetch_failed:{nome}"
_CHIAVE_ENERGIA = "sezione_zero:energia"


def aggiorna_e_genera_note(
    store: SeenStore,
    esiti_fonti: list[EsitoFonte],
    articoli_per_tema: dict[Tema, int],
    soglia: int = SOGLIA_RUN_CONSECUTIVI,
) -> list[NotaInterna]:
    """Aggiorna i contatori di run consecutivi e restituisce le note scattate.

    Va chiamata una volta per run. `articoli_per_tema` e' il conteggio (post-dedup)
    degli articoli per tema in questo run.
    """
    note: list[NotaInterna] = []

    # --- fetch_failed ripetuto per fonte (sez. 16.1) -------------------------
    for esito in esiti_fonti:
        chiave = _CHIAVE_FETCH.format(nome=esito.nome)
        if esito.stato == STATO_FETCH_FAILED:
            n = store.incrementa_contatore(chiave)
            if n >= soglia:
                note.append(
                    NotaInterna(
                        tipo=TipoNotaInterna.fetch_failed_ripetuto,
                        dettaglio=(
                            f"La fonte '{esito.nome}' e' in fetch_failed da {n} run "
                            "consecutivi: verifica manuale del feed."
                        ),
                    )
                )
        else:
            # fetch riuscito (anche con 0 voci): NON e' un fallimento -> reset.
            store.azzera_contatore(chiave)

    # --- sezione energia a zero ripetuta (sez. 16.3) -------------------------
    n_energia = articoli_per_tema.get(Tema.energia, 0)
    if n_energia == 0:
        n = store.incrementa_contatore(_CHIAVE_ENERGIA)
        if n >= soglia:
            note.append(
                NotaInterna(
                    tipo=TipoNotaInterna.sezione_a_zero_ripetuta,
                    dettaglio=(
                        f"La sezione energia e' a 0 articoli da {n} run consecutivi: "
                        "controllo manuale (fonte unica arXiv)."
                    ),
                )
            )
    else:
        store.azzera_contatore(_CHIAVE_ENERGIA)

    return note
