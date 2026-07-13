"""Adattatore per il modello Gemini (usato SOLO per la sintesi finale).

Espone una factory `crea_generatore()` che restituisce una funzione
`genera(prompt: str) -> dict`. Il resto della pipeline dipende solo da questa
callable, cosi' nei test si inietta un finto generatore senza rete ne' API key.

L'import di `google.genai` e' pigro: la libreria serve solo in modalita' reale.
"""
from __future__ import annotations

import json
import os
from typing import Callable, TypedDict

MODELLO_DEFAULT = "gemini-2.5-flash"

Generatore = Callable[[str], dict]


class _SchemaSintesi(TypedDict):
    """Schema di output passato a Gemini (response_schema).

    Vincola la generazione a JSON valido con esattamente questi campi: senza
    schema il modello puo' produrre JSON malformato (virgolette non escapate nel
    testo -> JSONDecodeError). `note` e' sempre presente ma puo' essere "".
    """

    sintesi: str
    perche_conta: str
    note: str


class GeminiNonConfigurato(RuntimeError):
    """Sollevata quando manca la API key per la modalita' con modello."""


def _estrai_json(testo: str) -> dict:
    """Estrae il primo oggetto JSON dalla risposta del modello.

    Anche con response_mime_type=application/json alcuni modelli avvolgono il
    JSON in un blocco markdown (```json ... ```) o aggiungono testo dopo
    l'oggetto: json.loads fallirebbe con "Extra data". Qui si cerca la prima
    graffa e si usa raw_decode, che legge un solo valore JSON e ignora tutto
    cio' che segue.
    """
    if not testo:
        raise ValueError("risposta vuota dal modello")
    inizio = testo.find("{")
    if inizio == -1:
        raise ValueError(f"nessun oggetto JSON nella risposta: {testo[:200]!r}")
    oggetto, _ = json.JSONDecoder().raw_decode(testo[inizio:])
    return oggetto


def _leggi_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise GeminiNonConfigurato(
            "Manca la API key di Gemini: imposta GEMINI_API_KEY (in locale nel file "
            ".env, in produzione come secret di GitHub Actions)."
        )
    return key


def crea_generatore(api_key: str | None = None, model: str = MODELLO_DEFAULT) -> Generatore:
    """Crea la callable di generazione basata su Gemini (structured JSON)."""
    key = _leggi_api_key(api_key)
    from google import genai  # import pigro: richiesto solo in modalita' reale

    client = genai.Client(api_key=key)

    def genera(prompt: str) -> dict:
        risposta = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                # constrained decoding: garantisce JSON valido con questi campi
                "response_schema": _SchemaSintesi,
            },
        )
        return _estrai_json(risposta.text)

    return genera
