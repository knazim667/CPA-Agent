from __future__ import annotations

import os
from typing import Any

import requests


class OpenRouterClient:
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, timeout: int = 120) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "CPA-Agent",
            "Content-Type": "application/json",
        }
        response = requests.post(
            f"{self.BASE_URL}/chat/completions",
            headers=headers,
            json={"model": self.model, "messages": messages},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload["choices"][0]["message"]["content"].strip()
