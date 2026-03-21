from __future__ import annotations

import json
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GoogleWorkspaceAuth:
    SCOPES = (
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    )

    def __init__(self, credentials_path: str | None = None) -> None:
        self.credentials_path = credentials_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self.oauth_client_path = os.getenv(
            "GOOGLE_OAUTH_CLIENT_SECRET_FILE",
            os.getenv("GOOGLE_OAUTH_CLIENT_FILE", "credentials/google-oauth-client.json"),
        )
        self.oauth_token_path = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "credentials/google-token.json")
        self.subject = os.getenv("GOOGLE_WORKSPACE_USER")
        self._credentials: Credentials | UserCredentials | None = None
        self._services: dict[str, Any] = {}

    def get_credentials(self) -> Credentials | UserCredentials:
        if self._credentials is None:
            if self._oauth_client_exists():
                self._credentials = self._load_oauth_credentials()
            elif not self.credentials_path:
                raise ValueError(
                    "Google credentials are not configured. "
                    "Set GOOGLE_OAUTH_CLIENT_SECRET_FILE for OAuth2 or "
                    "GOOGLE_SERVICE_ACCOUNT_FILE for service-account auth."
                )
            else:
                self._credentials = Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=self.SCOPES,
                )
                if self.subject:
                    self._credentials = self._credentials.with_subject(self.subject)
        return self._credentials

    def build_service(self, api_name: str, version: str):
        cache_key = f"{api_name}:{version}"
        if cache_key not in self._services:
            self._services[cache_key] = build(api_name, version, credentials=self.get_credentials())
        return self._services[cache_key]

    def authorize_oauth(self) -> str:
        credentials = self._run_oauth_flow()
        self._save_user_token(credentials)
        self._credentials = credentials
        self._services = {}
        return self.oauth_token_path

    def _oauth_client_exists(self) -> bool:
        return bool(self.oauth_client_path and os.path.exists(self.oauth_client_path))

    def _load_oauth_credentials(self) -> UserCredentials:
        credentials = None
        if os.path.exists(self.oauth_token_path):
            credentials = UserCredentials.from_authorized_user_file(self.oauth_token_path, self.SCOPES)
        if credentials and credentials.valid:
            return credentials
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_user_token(credentials)
            return credentials
        return self._run_oauth_flow()

    def _run_oauth_flow(self) -> UserCredentials:
        if not self._oauth_client_exists():
            raise ValueError(
                "OAuth client file not found. "
                "Set GOOGLE_OAUTH_CLIENT_SECRET_FILE to your desktop OAuth JSON file."
            )
        flow = InstalledAppFlow.from_client_secrets_file(self.oauth_client_path, self.SCOPES)
        credentials = flow.run_local_server(port=0)
        self._save_user_token(credentials)
        return credentials

    def _save_user_token(self, credentials: UserCredentials) -> None:
        token_path = self.oauth_token_path
        token_dir = os.path.dirname(token_path)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as handle:
            handle.write(credentials.to_json())

    def auth_summary(self) -> dict[str, str]:
        mode = "oauth2" if self._oauth_client_exists() else "service_account"
        return {
            "mode": mode,
            "oauth_client_path": self.oauth_client_path,
            "oauth_token_path": self.oauth_token_path,
            "service_account_path": self.credentials_path or "",
        }
