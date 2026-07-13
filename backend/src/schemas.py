"""Schema dati del digest (Pydantic) — beat "Infrastruttura & Hardware AI".

Riferimento di progettazione: Notion sezione 15 (schema) e sezione 16
(criteri di accettazione del Tester, 16.6 stati vuoti e 16.7 schema dati).

Principi vincolanti (CLAUDE.md):
- Il digest ha SEMPRE esattamente 5 sezioni, una per sotto-tema, anche vuote.
- Lo stato "nessun_aggiornamento" e' distinguibile a livello di schema (campo
  `stato`), non solo di testo, e usa un messaggio template fisso da codice
  (mai generato dal modello): vedi MESSAGGIO_NESSUN_AGGIORNAMENTO.
- `perche_conta` e' sempre obbligatorio e mai vuoto per ogni articolo.
- `fonti` e' una lista di coppie {nome, link} (supporta il caso multi-testata
  di Google News), mai due liste parallele.
- `note_interne` vive solo a livello di Digest, e' popolato solo da script e non
  viene MAI reso nella versione pubblica (sito/email): usa contenuto_pubblico().

A differenza dello starter, il Digest non e' assemblato dall'output strutturato
del modello: e' costruito dallo script (pipeline ~80% codice), quindi possiamo
applicare validazioni "dure" qui senza rischiare di rompere la lettura della
risposta del modello. Il modello contribuisce solo ai campi testuali dei singoli
articoli (sintesi, perche_conta, note).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Tema(str, Enum):
    """I 5 sotto-temi fissi del beat (enum vincolato, non testo libero)."""
    chip = "chip"
    data_center = "data_center"
    energia = "energia"
    supply_chain = "supply_chain"
    cloud_capacity = "cloud_capacity"


# Ordine canonico delle sezioni nel digest (pari peso di partenza, sezione 2).
TEMI_ORDINE: list[Tema] = [
    Tema.chip,
    Tema.data_center,
    Tema.energia,
    Tema.supply_chain,
    Tema.cloud_capacity,
]


class Stato(str, Enum):
    """Stato esplicito di una sezione (16.6: distinguibile a livello di schema)."""
    con_aggiornamenti = "con_aggiornamenti"
    nessun_aggiornamento = "nessun_aggiornamento"


class TipoNotaInterna(str, Enum):
    """Tipi di segnalazione operativa interna (sezione 15/16)."""
    fetch_failed_ripetuto = "fetch_failed_ripetuto"
    sezione_a_zero_ripetuta = "sezione_a_zero_ripetuta"


# Messaggio template FISSO per lo stato vuoto: vive nel codice, mai nel prompt,
# mai generato dal modello (16.6). Coerente col reminder email (sezione 17.1).
MESSAGGIO_NESSUN_AGGIORNAMENTO = "Nessun aggiornamento rilevante questa settimana."


class Fonte(BaseModel):
    """Coppia nome-link. Un articolo puo' avere piu' fonti (multi-testata)."""
    nome: str
    link: str

    @field_validator("nome", "link")
    @classmethod
    def _non_vuoto(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("nome e link della fonte non possono essere vuoti")
        return v


class Articolo(BaseModel):
    """Una singola voce del digest."""
    titolo: str
    fonti: list[Fonte] = Field(default_factory=list)
    data: str = ""
    sintesi: str
    perche_conta: str
    # Campo libero opzionale: es. "(preprint, non ancora sottoposto a peer
    # review)" per arXiv (14.8) o "ripreso da piu' testate" per Google News (14.7).
    note: str | None = None

    @field_validator("perche_conta")
    @classmethod
    def _perche_conta_obbligatorio(cls, v: str) -> str:
        # 16.7: perche_conta sempre valorizzato, mai vuoto/null.
        if not v or not v.strip():
            raise ValueError("perche_conta e' obbligatorio e non puo' essere vuoto")
        return v

    @field_validator("titolo")
    @classmethod
    def _titolo_non_vuoto(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("titolo non puo' essere vuoto")
        return v


class NotaInterna(BaseModel):
    """Segnalazione operativa per il team, generata solo da script (mai modello)."""
    tipo: TipoNotaInterna
    dettaglio: str


class Sezione(BaseModel):
    """Una delle 5 sezioni fisse del digest, con stato esplicito."""
    tema: Tema
    stato: Stato
    # Vuota se stato = nessun_aggiornamento (16.6).
    articoli: list[Articolo] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coerenza_stato_articoli(self) -> "Sezione":
        if self.stato is Stato.nessun_aggiornamento and self.articoli:
            raise ValueError(
                "una sezione 'nessun_aggiornamento' non puo' contenere articoli"
            )
        if self.stato is Stato.con_aggiornamenti and not self.articoli:
            raise ValueError(
                "una sezione 'con_aggiornamenti' deve contenere almeno un articolo"
            )
        return self


class Digest(BaseModel):
    """Il digest completo di una esecuzione settimanale."""
    data_generazione: str
    sezioni: list[Sezione]
    note_interne: list[NotaInterna] = Field(default_factory=list)

    @model_validator(mode="after")
    def _esattamente_cinque_temi(self) -> "Digest":
        # 16.7: esattamente 5 sezioni, una per tema, mai mancanti/duplicate/extra.
        temi = [s.tema for s in self.sezioni]
        if len(temi) != len(set(temi)):
            raise ValueError("temi duplicati tra le sezioni del digest")
        if set(temi) != set(TEMI_ORDINE):
            raise ValueError(
                "il digest deve avere esattamente le 5 sezioni fisse "
                f"({[t.value for t in TEMI_ORDINE]}), trovate: {[t.value for t in temi]}"
            )
        return self

    def sezione(self, tema: Tema) -> Sezione:
        """Ritorna la sezione del tema richiesto."""
        for s in self.sezioni:
            if s.tema is tema:
                return s
        raise KeyError(tema)  # impossibile dopo la validazione, difensivo

    def contenuto_pubblico(self) -> dict:
        """Versione destinata al lettore finale (sito/email): esclude sempre
        `note_interne`, che non deve mai comparire nel pubblico (16.7)."""
        dati = self.model_dump(mode="json")
        dati.pop("note_interne", None)
        return dati


def sezione_vuota(tema: Tema) -> Sezione:
    """Costruisce una sezione senza aggiornamenti (stato + nessun articolo)."""
    return Sezione(tema=tema, stato=Stato.nessun_aggiornamento, articoli=[])


def digest_vuoto(data_generazione: str) -> Digest:
    """Costruisce un digest con tutte e 5 le sezioni in 'nessun_aggiornamento'.

    Utile come scheletro da riempire e per la settimana senza alcuna novita'.
    """
    return Digest(
        data_generazione=data_generazione,
        sezioni=[sezione_vuota(t) for t in TEMI_ORDINE],
        note_interne=[],
    )
