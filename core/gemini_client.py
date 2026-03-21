from __future__ import annotations

import os
from typing import Any

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


class GeminiClient:
    SCOPES = (
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/generative-language.retriever",
    )

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout = timeout
        self.oauth_client_file = os.getenv("GOOGLE_GENAI_CLIENT_SECRET_FILE")
        self.oauth_token_file = os.getenv("GOOGLE_GENAI_TOKEN_FILE", "credentials/gemini-token.json")
        self.google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT")

    def chat(self, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        else:
            token = self._get_oauth_access_token()
            headers["Authorization"] = f"Bearer {token}"
            if self.google_cloud_project:
                headers["x-goog-user-project"] = self.google_cloud_project

        response = requests.post(
            url,
            headers=headers,
            json={
                "contents": [
                    {
                        "role": self._gemini_role(message["role"]),
                        "parts": [{"text": message["content"]}],
                    }
                    for message in messages
                ]
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        candidates = payload.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts).strip()

    def authorize_oauth(self) -> str:
        if not self.oauth_client_file:
            raise ValueError("GOOGLE_GENAI_CLIENT_SECRET_FILE is not configured.")
        flow = InstalledAppFlow.from_client_secrets_file(self.oauth_client_file, self.SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(self.oauth_token_file) or ".", exist_ok=True)
        with open(self.oauth_token_file, "w", encoding="utf-8") as handle:
            handle.write(creds.to_json())
        return self.oauth_token_file

    def _get_oauth_access_token(self) -> str:
        if not self.oauth_token_file or not os.path.exists(self.oauth_token_file):
            raise ValueError(
                "Gemini OAuth token not found. Run authorize_gemini_oauth.py "
                "or set GEMINI_API_KEY."
            )
        creds = Credentials.from_authorized_user_file(self.oauth_token_file, self.SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.oauth_token_file, "w", encoding="utf-8") as handle:
                    handle.write(creds.to_json())
            else:
                raise ValueError("Gemini OAuth token is invalid and cannot be refreshed.")
        return creds.token

    @staticmethod
    def _gemini_role(role: str) -> str:
        return "model" if role == "assistant" else "user"
