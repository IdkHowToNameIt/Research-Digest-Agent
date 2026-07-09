"""Adattatore per il modello Gemini (usato SOLO per la sintesi finale).

Espone una factory `crea_generatore()` che restituisce una funzione
`genera(prompt: str) -> dict`. Il resto della pipeline dipende solo da questa
callable, cosi' nei test si inietta un finto generatore senza rete ne' API key.

L'import di `google.genai` e' pigro: la libreria serve solo in modalita' reale.
"""
from __future__ import annotations

import json
import os
from typing import Callable

MODELLO_DEFAULT = "gemini-2.5-flash"

Generatore = Callable[[str], dict]


class GeminiNonConfigurato(RuntimeError):
    """Sollevata quando manca la API key per la modalita' con modello."""


def _leggi_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise GeminiNonConfigurato(
            "Manca la API key di Gemini (GEMINI_API_KEY). Usa la modalita' --demo "
            "per girare senza modello."
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
            config={"response_mime_type": "application/json"},
        )
        return json.loads(risposta.text)

    return genera
