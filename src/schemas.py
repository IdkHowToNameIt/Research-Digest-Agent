"""Schema dell'output del digest (Pydantic).

Uno schema ben definito è uno dei criteri di valutazione: il digest deve
SEMPRE rispettare questa forma. È anche ciò che impedisce all'agente di
"inventare" campi o restituire testo libero non strutturato.

Nota: i campi sono volutamente senza vincoli "duri" (lunghezze minime, numero
massimo di tag). L'output strutturato dei modelli non accetta tutti i vincoli
JSON Schema, e un vincolo violato farebbe fallire la lettura della risposta.
I controlli (es. al massimo 3 tag) sono applicati a runtime in main.py, dopo
aver ricevuto il digest.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DigestItem(BaseModel):
    """Una singola voce del digest."""
    titolo: str = Field(..., description="Titolo chiaro della novità")
    fonte: str = Field(..., description="Nome della fonte (es. nome del blog/sito)")
    url: str = Field(..., description="URL reale e funzionante della fonte")
    data: str = Field(default="", description="Data di pubblicazione, se disponibile")
    sintesi: str = Field(..., description="Sintesi in 2-4 frasi, in italiano")
    perche_conta: str = Field(..., description="Perché è rilevante per il beat/per KVA")
    tag: list[str] = Field(default_factory=list, description="1-3 tag tematici")


class Digest(BaseModel):
    """Il digest completo prodotto da una esecuzione."""
    beat: str = Field(..., description="Il tema presidiato")
    generato_il: str = Field(..., description="Timestamp ISO della generazione")
    voci: list[DigestItem] = Field(default_factory=list)
