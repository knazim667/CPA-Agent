from __future__ import annotations

import pytest
from skills.budget_engine import BudgetEngine

# Ledger row schema: [Date, Description, Category, Amount, Type, Reference, Notes]
LEDGER_ROWS = [
    ["2026-05-01", "Starbucks",     "Meals",     "45.00",  "Expense", "", ""],
    ["2026-05-05", "Client invoice","Sales",     "3000.00","Income",  "", ""],
    ["2026-05-10", "Facebook Ads",  "Marketing", "400.00", "Expense", "", ""],
    ["2026-05-15", "Google Ads",    "Marketing", "350.00", "Expense", "", ""],
    ["2026-05-20", "AWS",           "Software",  "89.00",  "Expense", "", ""],
    ["2026-04-05", "Office Depot",  "Marketing", "200.00", "Expense", "", ""],  # wrong month
]

BUDGETS = [
    {"id": "b1", "category": "Marketing", "amount": 500.0, "period": "monthly", "business_key": "biz_a"},
    {"id": "b2", "category": "Software",  "amount": 100.0, "period": "monthly", "business_key": "biz_a"},
    {"id": "b3", "category": "Meals",     "amount": 200.0, "period": "monthly", "business_key": "biz_a"},
]


# ── set_budget ─────────────────────────────────────────────────────────────────

def test_set_budget_returns_dict_with_id():
    engine = BudgetEngine()
    result = engine.set_budget("Marketing", 500.0, "monthly", "biz_a")
    assert result["id"] is not None
    assert result["category"] == "Marketing"
    assert result["amount"] == 500.0
    assert result["period"] == "monthly"


# ── compute_actuals ────────────────────────────────────────────────────────────

def test_compute_actuals_sums_expense_rows_only():
    engine = BudgetEngine()
    results = engine.compute_actuals(BUDGETS, LEDGER_ROWS, "2026-05")
    marketing = next(r for r in results if r["category"] == "Marketing")
    # Only May expense rows: 400 + 350 = 750 (April row excluded; Income row excluded)
    assert marketing["actual"] == pytest.approx(750.0, abs=0.01)


def test_compute_actuals_excludes_income_rows():
    engine = BudgetEngine()
    results = engine.compute_actuals(BUDGETS, LEDGER_ROWS, "2026-05")
    # Income of 3000 (Sales) should NOT appear in any budget's actuals
    for r in results:
        assert r["actual"] < 3000.0


def test_compute_actuals_excludes_wrong_month():
    engine = BudgetEngine()
    results = engine.compute_actuals(BUDGETS, LEDGER_ROWS, "2026-05")
    marketing = next(r for r in results if r["category"] == "Marketing")
    # April row (200) should NOT be included
    assert marketing["actual"] == pytest.approx(750.0, abs=0.01)


def test_compute_actuals_computes_remaining_and_pct():
    engine = BudgetEngine()
    results = engine.compute_actuals(BUDGETS, LEDGER_ROWS, "2026-05")
    software = next(r for r in results if r["category"] == "Software")
    assert software["budget"] == pytest.approx(100.0)
    assert software["actual"] == pytest.approx(89.0)
    assert software["remaining"] == pytest.approx(11.0, abs=0.01)
    assert software["pct"] == pytest.approx(89.0, abs=0.1)


def test_compute_actuals_zero_actual_when_no_spending():
    engine = BudgetEngine()
    results = engine.compute_actuals(BUDGETS, LEDGER_ROWS, "2026-05")
    meals = next(r for r in results if r["category"] == "Meals")
    assert meals["actual"] == pytest.approx(45.0, abs=0.01)
    assert meals["remaining"] == pytest.approx(155.0, abs=0.01)


def test_compute_actuals_returns_empty_for_bad_month():
    engine = BudgetEngine()
    results = engine.compute_actuals(BUDGETS, LEDGER_ROWS, "not-a-month")
    assert results == []


def test_compute_actuals_works_without_business_key():
    engine = BudgetEngine()
    budgets_no_key = [{"id": "x", "category": "Marketing", "amount": 500.0, "period": "monthly"}]
    results = engine.compute_actuals(budgets_no_key, LEDGER_ROWS, "2026-05")
    assert len(results) == 1
    assert results[0]["actual"] == pytest.approx(750.0, abs=0.01)


# ── get_alerts ─────────────────────────────────────────────────────────────────

def test_get_alerts_returns_warning_at_80_pct():
    engine = BudgetEngine()
    actuals = [{"id": "b1", "category": "Marketing", "budget": 500.0, "actual": 420.0, "remaining": 80.0, "pct": 84.0}]
    alerts = engine.get_alerts(actuals)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warning"


def test_get_alerts_returns_danger_at_100_pct():
    engine = BudgetEngine()
    actuals = [{"id": "b2", "category": "Software", "budget": 100.0, "actual": 105.0, "remaining": -5.0, "pct": 105.0}]
    alerts = engine.get_alerts(actuals)
    assert alerts[0]["level"] == "danger"


def test_get_alerts_returns_empty_below_80_pct():
    engine = BudgetEngine()
    actuals = [{"id": "b3", "category": "Meals", "budget": 200.0, "actual": 45.0, "remaining": 155.0, "pct": 22.5}]
    assert engine.get_alerts(actuals) == []


def test_get_alerts_includes_budget_id():
    engine = BudgetEngine()
    actuals = [{"id": "b1", "category": "Marketing", "budget": 500.0, "actual": 420.0, "remaining": 80.0, "pct": 84.0}]
    alerts = engine.get_alerts(actuals)
    assert alerts[0]["id"] == "b1"
