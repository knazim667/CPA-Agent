from __future__ import annotations

import os
from typing import Any

import requests


class OpenAIClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        self.organization = os.getenv("OPENAI_ORGANIZATION")
        self.project = os.getenv("OPENAI_PROJECT")

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if self.project:
            headers["OpenAI-Project"] = self.project

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.1,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload["choices"][0]["message"]["content"].strip()
