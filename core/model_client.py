from __future__ import annotations

import os

from core.gemini_client import GeminiClient
from core.ollama_client import OllamaClient
from core.openai_client import OpenAIClient


def get_model_client(*, purpose: str = "reasoning", reasoning_mode: str = "fast"):
    provider = os.getenv("MODEL_PROVIDER", "ollama").strip().lower()
    if provider == "openai":
        return OpenAIClient()
    if provider == "gemini":
        return GeminiClient()
    if purpose == "reflection":
        reflection_model = os.getenv("OLLAMA_REFLECTION_MODEL") or os.getenv("OLLAMA_AUDIT_MODEL")
        if reflection_model:
            return OllamaClient(model=reflection_model)
    if reasoning_mode == "quality":
        quality_model = os.getenv("OLLAMA_QUALITY_MODEL")
        if quality_model:
            return OllamaClient(model=quality_model)
    return OllamaClient()
