"""Metriche operative per run (osservabilità, sez. dashboard).

Ogni esecuzione della pipeline produce, oltre al digest editoriale, un insieme di
metriche OPERATIVE che la pipeline oggi calcola e butta via: stato di ogni fonte,
statistiche di deduplica, copertura dei 5 sotto-temi e — unica novità che va
CATTURATA a monte — l'uso di token del modello (costo). Qui le raccogliamo in un
record per run, persistito come un JSON per file (stesso pattern append-only
dell'archivio pubblico): un file nuovo a ogni run, quindi niente conflitti di
merge quando il workflow li ricommitta.

Perché un formato nuovo: nulla di tutto questo era finora persistito. Lo stato
delle fonti e gli esiti di dedup vivevano solo dentro un run e venivano scartati;
i token del modello non erano nemmeno letti (`risposta.usage` ignorato). Lo
storico della dashboard parte quindi dal primo run dopo l'introduzione di questo
modulo (nessun retro-fill possibile): vedi DECISIONI.md.

Separazione delle responsabilità:
- `RaccoltaMetriche` accumula i dati durante il run. L'uso di token le arriva da
  una callback (`registra_uso`) passata a `crea_generatore`, così `llm.py` non
  dipende da questo modulo; i dati operativi glieli passa la pipeline alla fine.
- `finalizza()` produce il record immutabile (`MetricheRun`), applicando il
  listino prezzi (€/1M token) per la stima di costo.
- `salva_metriche`/`carica_metriche` sono l'I/O, gemelle di quelle dell'archivio.

Nessun dato sensibile o nota interna entra qui: sono numeri operativi. La
dashboard che li mostra è comunque servita da un sito pubblico (vedi DECISIONI):
i costi del free tier sono ~0 e in produzione il sito gira in intranet.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .schemas import TEMI_ORDINE, Digest, Tema
from .consegna.note_interne import _CHIAVE_ENERGIA, _CHIAVE_FETCH
from .raccolta.dedup import EsitoCandidato
from .raccolta.fetch import STATO_FETCH_FAILED, Candidato, EsitoFonte
from .state import SeenStore


# --- schema del record per run ---------------------------------------------
class UsoModello(BaseModel):
    """Uso di token e costo stimato per un singolo modello nel run."""
    modello: str
    chiamate: int
    prompt_tokens: int
    completion_tokens: int
    costo_stimato: float


class Costo(BaseModel):
    """Riepilogo di costo del run (somma sui modelli usati nella cascata)."""
    modelli: list[UsoModello] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    costo_stimato: float = 0.0


class StatoFonte(BaseModel):
    """Esito del fetch di una fonte in questo run + run consecutivi falliti."""
    nome: str
    stato: str                      # "ok" | "fetch_failed"
    errore: str | None = None
    n_candidati: int = 0
    consecutivi_falliti: int = 0    # contatore corrente dopo questo run


class Dedup(BaseModel):
    """Statistiche del filtro anti-duplicati + scarto in classificazione."""
    raccolti: int = 0               # candidati totali dalle fonti (pre-dedup)
    nuovi: int = 0                  # nessun simile sopra soglia
    aggiornamenti: int = 0          # alto overlap ma novità legittima (inclusi)
    duplicati_esatti: int = 0       # hash già visto (scartati)
    duplicati_fuzzy: int = 0        # simile sopra soglia senza segnali (scartati)
    scartati_classificazione: int = 0  # tenuti dal dedup ma fuori beat/tema None
    pubblicati: int = 0             # articoli effettivamente nel digest


class CoperturaTema(BaseModel):
    """Copertura di un sotto-tema nel run (stato + numero articoli)."""
    tema: str
    stato: str                      # "con_aggiornamenti" | "nessun_aggiornamento"
    n_articoli: int = 0


class MetricheRun(BaseModel):
    """Metriche operative di una singola esecuzione (un file per run)."""
    timestamp: str                  # ISO UTC del run (con orario: identità del run)
    data_generazione: str           # data del digest (correla con l'archivio)
    fonti: list[StatoFonte] = Field(default_factory=list)
    dedup: Dedup = Field(default_factory=Dedup)
    copertura: list[CoperturaTema] = Field(default_factory=list)
    energia_zero_consecutivi: int = 0
    costo: Costo = Field(default_factory=Costo)

    def nome_file(self) -> str:
        """Nome di file sicuro su ogni OS (niente ':' del timestamp ISO)."""
        return f"{self.timestamp.replace(':', '-')}.json"


# --- raccolta durante il run -----------------------------------------------
def _stima_costo(prezzi: dict, modello: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Costo stimato (€) per un modello dato il listino €/1M token.

    `prezzi` = {modello_id: {"input": €/1M, "output": €/1M}}. Un modello assente dal
    listino (o il free tier, prezzi a 0) contribuisce 0: i token restano contati
    comunque, così passando all'API a pagamento basta valorizzare il listino.
    """
    tariffa = prezzi.get(modello, {})
    inp = float(tariffa.get("input", 0.0))
    out = float(tariffa.get("output", 0.0))
    return prompt_tokens / 1_000_000 * inp + completion_tokens / 1_000_000 * out


class RaccoltaMetriche:
    """Accumulatore mutabile delle metriche di un run.

    L'uso di token arriva via `registra_uso` (callback del generatore, una volta
    per chiamata riuscita al modello); i dati operativi via `registra_run` alla
    fine della pipeline. `finalizza` cristallizza il tutto in un `MetricheRun`.
    """

    def __init__(self) -> None:
        # modello -> [chiamate, prompt_tokens, completion_tokens]
        self._uso: dict[str, list[int]] = {}
        self._fonti: list[StatoFonte] = []
        self._dedup = Dedup()
        self._copertura: list[CoperturaTema] = []
        self._energia_zero = 0

    # uso token (callback dal generatore in llm.py) --------------------------
    def registra_uso(self, modello: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Somma i token di una singola chiamata riuscita al modello `modello`."""
        acc = self._uso.setdefault(modello, [0, 0, 0])
        acc[0] += 1
        acc[1] += int(prompt_tokens or 0)
        acc[2] += int(completion_tokens or 0)

    # dati operativi (chiamati dalla pipeline a fine run) --------------------
    def registra_run(
        self,
        *,
        candidati: list[Candidato],
        esiti_fonti: list[EsitoFonte],
        esiti_dedup: list[EsitoCandidato],
        scartati_classificazione: int,
        pubblicati: int,
        digest: Digest,
        store: SeenStore,
    ) -> None:
        """Registra stato fonti, statistiche dedup e copertura del run."""
        self._fonti = [
            StatoFonte(
                nome=e.nome,
                stato=e.stato,
                errore=e.errore,
                n_candidati=len(e.candidati),
                consecutivi_falliti=(
                    store.leggi_contatore(_CHIAVE_FETCH.format(nome=e.nome))
                    if e.stato == STATO_FETCH_FAILED else 0
                ),
            )
            for e in esiti_fonti
        ]

        conteggio: dict[str, int] = {}
        for esito in esiti_dedup:
            conteggio[esito.decisione] = conteggio.get(esito.decisione, 0) + 1
        self._dedup = Dedup(
            raccolti=len(candidati),
            nuovi=conteggio.get("nuovo", 0),
            aggiornamenti=conteggio.get("aggiornamento", 0),
            duplicati_esatti=conteggio.get("duplicato_esatto", 0),
            duplicati_fuzzy=conteggio.get("duplicato", 0),
            scartati_classificazione=scartati_classificazione,
            pubblicati=pubblicati,
        )

        self._copertura = [
            CoperturaTema(
                tema=tema.value,
                stato=digest.sezione(tema).stato.value,
                n_articoli=len(digest.sezione(tema).articoli),
            )
            for tema in TEMI_ORDINE
        ]
        self._energia_zero = store.leggi_contatore(_CHIAVE_ENERGIA)

    # cristallizzazione ------------------------------------------------------
    def finalizza(self, prezzi: dict, data_generazione: str, timestamp: str) -> MetricheRun:
        """Produce il record immutabile del run, applicando il listino prezzi."""
        modelli = [
            UsoModello(
                modello=m,
                chiamate=acc[0],
                prompt_tokens=acc[1],
                completion_tokens=acc[2],
                costo_stimato=round(_stima_costo(prezzi, m, acc[1], acc[2]), 6),
            )
            for m, acc in sorted(self._uso.items())
        ]
        costo = Costo(
            modelli=modelli,
            prompt_tokens=sum(u.prompt_tokens for u in modelli),
            completion_tokens=sum(u.completion_tokens for u in modelli),
            costo_stimato=round(sum(u.costo_stimato for u in modelli), 6),
        )
        return MetricheRun(
            timestamp=timestamp,
            data_generazione=data_generazione,
            fonti=self._fonti,
            dedup=self._dedup,
            copertura=self._copertura,
            energia_zero_consecutivi=self._energia_zero,
            costo=costo,
        )


# --- I/O (gemelle dell'archivio) -------------------------------------------
def salva_metriche(record: MetricheRun, dir_metriche: str) -> str:
    """Salva il record di un run come JSON (un file per run). Ritorna il percorso."""
    p = Path(dir_metriche)
    p.mkdir(parents=True, exist_ok=True)
    percorso = p / record.nome_file()
    percorso.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return str(percorso)


def carica_metriche(dir_metriche: str) -> list[MetricheRun]:
    """Carica tutti i record metriche salvati, ordinati per timestamp crescente."""
    p = Path(dir_metriche)
    if not p.exists():
        return []
    record = [MetricheRun.model_validate_json(f.read_text(encoding="utf-8"))
              for f in p.glob("*.json")]
    return sorted(record, key=lambda r: r.timestamp)


# --- dati per la dashboard del sito (contratto col frontend) ----------------
# File pubblicato nella publish-dir e letto via fetch dalla dashboard. Diverso da
# data.json (contenuto editoriale): qui vivono le metriche operative per run.
NOME_FILE_DASHBOARD = "metriche.json"


def costruisci_dati_dashboard(record: list[MetricheRun]) -> dict:
    """Contratto dati della dashboard di osservabilità.

    A differenza dell'archivio (che il sito spezza in indice + bucket per non
    scaricare tutta la storia), le metriche sono un record leggero per run e a
    bassa frequenza (uno a settimana): stanno comodamente in un unico file, che il
    frontend filtra per periodo lato client — stessa logica dei gruppi-giorno.

    Forma:
        {
          "generato": "<timestamp ISO dell'ultimo run>",
          "temi": ["chip","data_center",...],   # ordine canonico per l'asse UI
          "run": [ <MetricheRun>, ... ]          # dal più recente al più vecchio
        }
    """
    runs = sorted(record, key=lambda r: r.timestamp, reverse=True)
    return {
        "generato": runs[0].timestamp if runs else "",
        "temi": [t.value for t in TEMI_ORDINE],
        "run": [r.model_dump(mode="json") for r in runs],
    }


def scrivi_dashboard(record: list[MetricheRun], out_dir: str) -> str:
    """Scrive `metriche.json` nella publish-dir del sito. Ritorna il percorso.

    Va invocata DOPO `genera_sito` (che svuota la publish-dir): così il file
    sopravvive e riflette l'intero storico a ogni run.
    """
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    percorso = p / NOME_FILE_DASHBOARD
    percorso.write_text(
        json.dumps(costruisci_dati_dashboard(record), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(percorso)
