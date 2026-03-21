from __future__ import annotations

import os
from typing import Any

from core.google_auth import GoogleWorkspaceAuth


class GoogleDocsManager:
    def __init__(self, credentials_path: str | None = None) -> None:
        self.credentials_path = credentials_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self.auth = GoogleWorkspaceAuth(self.credentials_path)
        self._docs_service = None

    def _get_docs_service(self):
        if self._docs_service is None:
            self._docs_service = self.auth.build_service("docs", "v1")
        return self._docs_service

    def create_document(self, title: str, initial_text: str | None = None) -> dict[str, Any]:
        document = self._get_docs_service().documents().create(body={"title": title}).execute()
        if initial_text:
            self.append_text(document["documentId"], initial_text)
        return document

    def get_document(self, document_id: str) -> dict[str, Any]:
        return self._get_docs_service().documents().get(documentId=document_id).execute()

    def append_text(self, document_id: str, text: str) -> dict[str, Any]:
        document = self.get_document(document_id)
        end_index = document["body"]["content"][-1]["endIndex"] - 1
        return self._get_docs_service().documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": end_index},
                            "text": text if text.endswith("\n") else f"{text}\n",
                        }
                    }
                ]
            },
        ).execute()
