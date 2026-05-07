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
    mock_agent.sheets = MagicMock()
    mock_agent.LEDGER_HEADERS = ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]
    mock_agent._safe_float = lambda x: float(x) if x else 0.0
    mock_agent._normalize_row = lambda row: list(row[:7]) if isinstance(row, (list, tuple)) else row
    mock_agent.get_status.return_value = {
        "active_business_key": "biz_a",
        "active_business": {"business_name": "Biz A", "google_sheet_id": "", "google_doc_id": "", "state": ""},
        "businesses": [{"key": "biz_a", "business_name": "Biz A"}],
        "conversation": [], "workspace_boot_error": None, "input_mode": "text",
        "model_config": {"provider": "ollama", "reasoning_mode": "fast", "reasoning_model": "llama3", "reflection_model": "llama3"},
        "dashboard": {"transaction_count": 0, "income_total": 0.0, "expense_total": 0.0, "flagged_actions": 0, "recent_transactions": [], "recent_audits": []},
        "learned_source_count": 0,
    }

    import auth
    import web_app
    web_app.agent = mock_agent
    from web_app import app

    def _fake_owner():
        return {"id": 1, "username": "testowner", "role": "owner", "is_active": True,
                "email": "test@test.com", "created_at": "2026-01-01"}

    app.dependency_overrides[auth.get_current_user] = _fake_owner
    app.dependency_overrides[auth.require_owner] = _fake_owner
    app.dependency_overrides[auth.require_owner_or_bookkeeper] = _fake_owner

    yield TestClient(app)

    app.dependency_overrides.clear()


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


def test_pl_report_returns_category_totals(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Client A", "Consulting", "5000.00", "Income", "", ""],
        ["2026-01-15", "Supplies", "Office", "200.00", "Expense", "", ""],
        ["2026-02-01", "Software", "SaaS", "50.00", "Expense", "", ""],
    ]
    client.app.state  # touch to ensure app is initialized
    import web_app
    web_app.agent.sheets.read_range.return_value = rows
    web_app.agent.memory.get_current_business.return_value = {"business_name": "Biz A", "google_sheet_id": "sheet-id"}
    response = client.get("/api/report/pl")
    assert response.status_code == 200
    data = response.json()
    assert data["income_total"] == 5000.0
    assert data["expense_total"] == 250.0
    assert data["net"] == 4750.0


def test_pl_report_date_filter(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Jan sale", "Sales", "1000.00", "Income", "", ""],
        ["2026-03-05", "Mar sale", "Sales", "2000.00", "Income", "", ""],
    ]
    import web_app
    web_app.agent.sheets.read_range.return_value = rows
    web_app.agent.memory.get_current_business.return_value = {"business_name": "Biz A", "google_sheet_id": "sheet-id"}
    response = client.get("/api/report/pl?from_date=2026-02-01")
    assert response.json()["income_total"] == 2000.0


def test_export_csv_returns_csv_file(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Sale", "Consulting", "500.00", "Income", "", ""],
    ]
    import web_app
    web_app.agent.sheets.read_range.return_value = rows
    web_app.agent.memory.get_current_business.return_value = {"business_name": "Biz A", "google_sheet_id": "sheet-id"}
    web_app.agent.memory.current_business_key = "biz_a"
    response = client.get("/api/export/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert "Sale" in response.text


def test_ledger_returns_paginated_rows(client):
    rows = [["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]]
    for i in range(25):
        rows.append([f"2026-01-{(i % 28) + 1:02d}", f"Item {i}", "Office", "10.00", "Expense", "", ""])
    import web_app
    web_app.agent.sheets.read_range.return_value = rows
    web_app.agent.memory.get_current_business.return_value = {"business_name": "Biz A", "google_sheet_id": "sheet-id"}
    response = client.get("/api/ledger?page=1&page_size=20")
    data = response.json()
    assert data["total_count"] == 25
    assert len(data["rows"]) == 20
    assert data["total_pages"] == 2


def test_ledger_search_filter(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Coffee shop", "Meals", "15.00", "Expense", "", ""],
        ["2026-01-11", "Office supplies", "Office", "50.00", "Expense", "", ""],
    ]
    import web_app
    web_app.agent.sheets.read_range.return_value = rows
    web_app.agent.memory.get_current_business.return_value = {"business_name": "Biz A", "google_sheet_id": "sheet-id"}
    response = client.get("/api/ledger?search=coffee")
    data = response.json()
    assert data["total_count"] == 1
    assert data["rows"][0][1] == "Coffee shop"


def test_category_suggest_returns_match(client):
    import web_app
    web_app.agent.categorization.suggest_category.return_value = {
        "category": "Meals & Entertainment", "confidence": 0.95, "rule_id": "r1"
    }
    response = client.get("/api/category/suggest?description=Starbucks")
    assert response.status_code == 200
    assert response.json()["category"] == "Meals & Entertainment"


def test_category_suggest_requires_description(client):
    response = client.get("/api/category/suggest")
    assert response.status_code == 400


def test_save_category_rule(client):
    import web_app
    web_app.agent.categorization.save_rule.return_value = {
        "id": "r1", "pattern": "starbucks", "category": "Meals & Entertainment",
        "confidence": 0.8, "use_count": 1,
    }
    response = client.post(
        "/api/category-rule",
        json={"description": "Starbucks", "category": "Meals & Entertainment"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    web_app.agent._save_category_rules.assert_called_once()


def test_get_recurring_returns_schedules(client):
    import web_app
    web_app.agent.recurring.list_schedules.return_value = [
        {"id": "1", "description": "Rent", "amount": 2000.0, "category": "Rent",
         "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
         "next_date": "2026-05-01", "active": True, "last_posted_date": None}
    ]
    response = client.get("/api/recurring")
    assert response.status_code == 200
    assert len(response.json()["schedules"]) == 1


def test_delete_recurring_not_found(client):
    import web_app
    web_app.agent.recurring.cancel_schedule.return_value = False
    response = client.delete("/api/recurring/nonexistent-id")
    assert response.status_code == 404
