from __future__ import annotations

import pytest
from skills.financial_statements import FinancialStatements

# Ledger row schema: [Date, Description, Category, Amount, Type, Reference, Notes]
LEDGER_ROWS = [
    ["2026-01-10", "Client payment", "Consulting", "5000.00", "Income", "", ""],
    ["2026-01-15", "Office rent",    "Rent",       "2000.00", "Expense", "", ""],
    ["2026-02-01", "Software sub",   "Software",   "50.00",  "Expense", "", ""],
    ["2026-03-10", "Equipment",      "Equipment",  "800.00", "Expense", "", ""],
]


# ── Balance Sheet ──────────────────────────────────────────────────────────────

def test_balance_sheet_net_income():
    fs = FinancialStatements()
    result = fs.compute_balance_sheet(LEDGER_ROWS)
    # YTD: income 5000, expenses 2050+800 = 2850, net = 2150
    assert result["equity"]["retained_earnings"] == pytest.approx(2150.0, abs=0.01)


def test_balance_sheet_cash_equals_net_income_without_ar_ap():
    fs = FinancialStatements()
    result = fs.compute_balance_sheet(LEDGER_ROWS)
    assert result["assets"]["cash"] == pytest.approx(result["equity"]["retained_earnings"], abs=0.01)


def test_balance_sheet_approximate_flag_set_without_ar_ap():
    fs = FinancialStatements()
    result = fs.compute_balance_sheet(LEDGER_ROWS)
    assert result["approximate"] is True


def test_balance_sheet_with_ar_ap():
    fs = FinancialStatements()
    ar_ap = {
        "receivables": [{"amount": 1000.0, "status": "open"}],
        "payables":    [{"amount": 500.0,  "status": "open"}],
    }
    result = fs.compute_balance_sheet(LEDGER_ROWS, ar_ap_data=ar_ap)
    assert result["assets"]["accounts_receivable"] == pytest.approx(1000.0)
    assert result["liabilities"]["accounts_payable"] == pytest.approx(500.0)
    assert result["approximate"] is False


def test_balance_sheet_empty_ledger():
    fs = FinancialStatements()
    result = fs.compute_balance_sheet([])
    assert result["assets"]["total"] == 0.0
    assert result["equity"]["total"] == 0.0


def test_balance_sheet_balanced_flag():
    fs = FinancialStatements()
    result = fs.compute_balance_sheet(LEDGER_ROWS)
    # Assets = Cash (net_income) + 0 AR = net_income
    # Liabilities = 0; Equity = net_income
    # Assets - Liabilities - Equity = 0 → balanced
    assert result["balanced"] is True


# ── Cash Flow ──────────────────────────────────────────────────────────────────

def test_cash_flow_operating_income_is_positive():
    fs = FinancialStatements()
    # Consulting income in January
    rows = [["2026-01-10", "Client payment", "Consulting", "5000.00", "Income", "", ""]]
    result = fs.compute_cash_flow(rows, "2026-01-01", "2026-12-31")
    assert result["operating"] > 0


def test_cash_flow_expense_reduces_operating():
    fs = FinancialStatements()
    rows = [["2026-01-15", "Office rent", "Rent", "2000.00", "Expense", "", ""]]
    result = fs.compute_cash_flow(rows, "2026-01-01", "2026-12-31")
    assert result["operating"] < 0


def test_cash_flow_equipment_is_investing():
    fs = FinancialStatements()
    rows = [["2026-03-10", "Laptop", "Equipment", "800.00", "Expense", "", ""]]
    result = fs.compute_cash_flow(rows, "2026-01-01", "2026-12-31")
    assert result["investing"] < 0
    assert result["operating"] == 0.0


def test_cash_flow_date_filter():
    fs = FinancialStatements()
    # Only Q1 — the equipment row (March) should be included
    result = fs.compute_cash_flow(LEDGER_ROWS, "2026-01-01", "2026-03-31")
    net = result["operating"] + result["investing"] + result["financing"]
    assert result["net_change"] == pytest.approx(net, abs=0.01)


def test_cash_flow_excludes_out_of_range_rows():
    fs = FinancialStatements()
    # Narrow window: only January
    result = fs.compute_cash_flow(LEDGER_ROWS, "2026-01-01", "2026-01-31")
    # Q1 has 5000 income and 2000 rent in Jan; Feb software sub should be excluded
    assert result["operating"] == pytest.approx(5000.0 - 2000.0, abs=0.01)


def test_cash_flow_net_change_is_sum_of_activities():
    fs = FinancialStatements()
    result = fs.compute_cash_flow(LEDGER_ROWS, "2026-01-01", "2026-12-31")
    expected = result["operating"] + result["investing"] + result["financing"]
    assert result["net_change"] == pytest.approx(expected, abs=0.01)
