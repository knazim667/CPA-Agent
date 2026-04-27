from __future__ import annotations
import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")

    mock_agent = MagicMock()
    mock_agent.workspace_boot_error = None
    mock_agent.input_mode = "text"
    mock_agent.memory = MagicMock()
    mock_agent.memory.current_business_key = "biz_a"
    mock_agent.get_status.return_value = {
        "active_business_key": "biz_a",
        "active_business": {"business_name": "Biz A", "google_sheet_id": "", "google_doc_id": "", "state": ""},
        "businesses": [{"key": "biz_a", "business_name": "Biz A"}],
        "conversation": [], "workspace_boot_error": None, "input_mode": "text",
        "model_config": {"provider": "ollama", "reasoning_mode": "fast", "reasoning_model": "llama3", "reflection_model": "llama3"},
        "dashboard": {"transaction_count": 0, "income_total": 0.0, "expense_total": 0.0, "flagged_actions": 0, "recent_transactions": [], "recent_audits": []},
        "learned_source_count": 0,
    }

    import web_app
    web_app.agent = mock_agent
    from web_app import app
    yield TestClient(app)


def test_provider_switch_to_openrouter(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    response = client.post("/api/provider", json={"provider": "openrouter"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_provider_switch_rejects_invalid(client):
    response = client.post("/api/provider", json={"provider": "banana"})
    assert response.status_code == 400


def test_provider_switch_to_openai(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = client.post("/api/provider", json={"provider": "openai"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
