from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "MODEL_PROVIDER", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
        "OPENAI_API_KEY", "OPENAI_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL",
        "OLLAMA_MODEL", "OLLAMA_QUALITY_MODEL", "OLLAMA_REFLECTION_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def sample_ledger_rows():
    return [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Client payment", "Sales", "5000.00", "Income", "INV-001", ""],
        ["2026-01-15", "Office supplies", "Office", "200.00", "Expense", "REC-001", ""],
        ["2026-02-01", "Software sub", "Software", "50.00", "Expense", "REC-002", ""],
    ]
