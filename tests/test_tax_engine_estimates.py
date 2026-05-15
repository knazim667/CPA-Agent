import pytest
from unittest.mock import patch
from datetime import date
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from tax_engine import TaxEngine


class MockMemoryManager:
    def __init__(self):
        self.current_business_key = "test_business"
        self.long_term_dir = Path("/tmp/test_long_term")

    def get_current_business(self):
        return {"business_name": "Test Business"}

    def load_category_rules(self):
        return {"rules": []}

    def load_recurring(self):
        return {"schedules": []}


def test_get_quarterly_estimate():
    result = TaxEngine(MockMemoryManager()).get_quarterly_estimate(100000.0, 2026)
    assert "se_tax" in result
    assert "federal_tax" in result
    assert "total" in result
    assert "due_date" in result
    assert "quarter" in result
    assert result["year"] == 2026
    assert result["quarter"] in ["Q1", "Q2", "Q3", "Q4"]
    assert result["total"] == round(result["se_tax"] + result["federal_tax"], 2)


def test_get_quarterly_estimate_quarter_determination():
    engine = TaxEngine(MockMemoryManager())
    with patch('tax_engine.date') as mock_date:
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        mock_date.today.return_value = date(2026, 2, 15)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q1"
        assert result["due_date"] == "2026-04-15"

        mock_date.today.return_value = date(2026, 4, 30)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q2"
        assert result["due_date"] == "2026-06-15"

        mock_date.today.return_value = date(2026, 7, 15)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q3"
        assert result["due_date"] == "2026-09-15"

        mock_date.today.return_value = date(2026, 10, 15)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q4"
        assert result["due_date"] == "2027-01-15"


def test_get_irs_deadlines():
    deadlines = TaxEngine(MockMemoryManager()).get_irs_deadlines(2026)
    assert len(deadlines) == 5
    assert deadlines[0]["deadline"] == "2026-04-15"
    assert deadlines[0]["quarter"] == "Q1"
    assert deadlines[0]["description"] == "Q1 Estimated Tax Payment"
    assert deadlines[1]["deadline"] == "2026-06-15"
    assert deadlines[1]["quarter"] == "Q2"
    assert deadlines[2]["deadline"] == "2026-09-15"
    assert deadlines[2]["quarter"] == "Q3"
    assert deadlines[3]["deadline"] == "2027-01-15"
    assert deadlines[3]["quarter"] == "Q4"
    assert deadlines[4]["deadline"] == "2027-04-15"
    assert deadlines[4]["quarter"] == "Annual"
    assert deadlines[4]["description"] == "Annual Tax Return Due"


def test_get_upcoming_alerts():
    engine = TaxEngine(MockMemoryManager())
    with patch('tax_engine.date') as mock_date:
        mock_date.today.return_value = date(2026, 4, 1)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        alerts = engine.get_upcoming_alerts(days_ahead=30)
        assert len(alerts) >= 1
        assert any(a["quarter"] == "Q1" for a in alerts)
        assert all(a["days_until"] <= 30 for a in alerts)


def test_get_upcoming_alerts_no_deadlines():
    engine = TaxEngine(MockMemoryManager())
    with patch('tax_engine.date') as mock_date:
        mock_date.today.return_value = date(2026, 5, 1)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        alerts = engine.get_upcoming_alerts(days_ahead=30)
        assert len(alerts) == 0


def test_compute_tax_summary():
    engine = TaxEngine(MockMemoryManager())
    ledger_rows = [
        ["2026-01-01", "Client payment", "Services", "Income", "5000.00", "", ""],
        ["2026-01-15", "Another payment", "Services", "Income", "3000.00", "", ""],
        ["2026-01-20", "Office supplies", "Office", "Expense", "500.00", "", ""],
        ["2026-02-01", "Software", "Software", "Expense", "200.00", "", ""],
    ]
    result = engine.compute_tax_summary(ledger_rows)
    assert result["total_income"] == 8000.0
    assert result["total_expenses"] == 700.0
    assert result["net_income"] == 7300.0
    assert "se_tax" in result
    assert "federal_tax" in result
    assert "total_tax" in result
    assert "estimated_quarterly_payment" in result


def test_compute_tax_summary_empty():
    result = TaxEngine(MockMemoryManager()).compute_tax_summary([])
    assert result["total_income"] == 0.0
    assert result["total_expenses"] == 0.0
    assert result["net_income"] == 0.0
    assert result["se_tax"] == 0.0
    assert result["federal_tax"] == 0.0
    assert result["total_tax"] == 0.0


def test_compute_tax_summary_invalid_rows():
    engine = TaxEngine(MockMemoryManager())
    ledger_rows = [
        ["2026-01-01", "Client payment", "Services", "Income", "5000.00", "", ""],
        ["short_row"],
        ["2026-01-20", "Office", "Office", "Expense", "not_a_number", "", ""],
        ["2026-01-21", "Another", "Services", "Income", "", "", ""],
    ]
    result = engine.compute_tax_summary(ledger_rows)
    assert result["total_income"] == 5000.0
    assert result["total_expenses"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__])
