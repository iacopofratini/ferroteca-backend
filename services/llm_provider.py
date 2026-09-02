"""Unico punto di accesso all'SDK del provider LLM/embedding.

Tutto il resto del backend (rag.py, sync_documents.py, reindex_ieac_accm.py,
il futuro modulo training) deve chiamare `embed()` e `generate()` da qui,
mai importare l'SDK Gemini direttamente. Cambiare provider in futuro
significa toccare solo questo file.

Il provider oggi è Gemini, scelto solo per costo in fase di test (vedi
docs/AUDIT.md, punto 3.1) — è provvisorio.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import List

from google import genai
from google.genai import types
from langchain_google_genai import GoogleGenerativeAIEmbeddings

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONALITY = 768
GENERATION_MODEL = "gemini-2.5-flash"

_MAX_RETRIES = 5
_RETRY_WAIT_SECONDS = 60


class LLMProvider(ABC):
    @abstractmethod
    def embed(self, texts: List[str], *, output_dimensionality: int = EMBEDDING_DIMENSIONALITY) -> List[List[float]]:
        ...

    @abstractmethod
    def generate(self, prompt: str, *, temperature: float = 0.1, max_output_tokens: int = 8192) -> str:
        ...


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str = GEMINI_API_KEY):
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY non impostata")
        self._api_key = api_key
        self._client = genai.Client(api_key=api_key)

    def _embedder(self) -> GoogleGenerativeAIEmbeddings:
        return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=self._api_key)

    def embed(self, texts: List[str], *, output_dimensionality: int = EMBEDDING_DIMENSIONALITY) -> List[List[float]]:
        embedder = self._embedder()
        for attempt in range(_MAX_RETRIES):
            try:
                return embedder.embed_documents(texts, output_dimensionality=output_dimensionality)
            except Exception as exc:
                if "429" in str(exc) and attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_WAIT_SECONDS)
                    continue
                raise
        raise RuntimeError("embed: numero massimo di tentativi superato")

    def generate(self, prompt: str, *, temperature: float = 0.1, max_output_tokens: int = 8192) -> str:
        response = self._client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )
        return response.text


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider


def embed(texts: List[str], *, output_dimensionality: int = EMBEDDING_DIMENSIONALITY) -> List[List[float]]:
    return get_provider().embed(texts, output_dimensionality=output_dimensionality)


def generate(prompt: str, *, temperature: float = 0.1, max_output_tokens: int = 8192) -> str:
    return get_provider().generate(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
