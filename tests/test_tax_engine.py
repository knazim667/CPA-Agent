import pytest
from unittest.mock import Mock, patch
from datetime import date, timedelta
from pathlib import Path
import sys
import os

# Add the skills directory to the path
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


def test_tax_engine_initialization():
    """Test that TaxEngine initializes correctly"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    assert engine.memory == mock_memory


def test_compute_se_tax_zero_income():
    """Test SE tax with zero income"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    result = engine.compute_se_tax(0.0)
    assert result == 0.0

    result = engine.compute_se_tax(-1000.0)
    assert result == 0.0


def test_compute_se_tax_positive_income():
    """Test SE tax with positive income"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # SE tax = net_income * 0.9235 * 0.153
    result = engine.compute_se_tax(100000.0)
    expected = 100000.0 * 0.9235 * 0.153
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_zero_income():
    """Test federal tax with zero income"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    result = engine.compute_estimated_federal(0.0)
    assert result == 0.0


def test_compute_estimated_federal_10_percent_bracket():
    """Test federal tax in 10% bracket"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # $5,000 - all in 10% bracket
    result = engine.compute_estimated_federal(5000.0)
    assert round(result, 2) == round(5000.0 * 0.10, 2)


def test_compute_estimated_federal_12_percent_bracket():
    """Test federal tax spans 10% and 12% brackets"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # $15,000 - spans 10% and 12% brackets
    # 10% on first $11,600 = $1,160
    # 12% on remaining $3,400 = $408
    # Total = $1,568
    result = engine.compute_estimated_federal(15000.0)
    expected = (11600 * 0.10) + ((15000 - 11600) * 0.12)
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_22_percent_bracket():
    """Test federal tax spans 10%, 12%, and 22% brackets"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # $50,000 - spans 10%, 12%, and 22% brackets
    # 10% on first $11,600 = $1,160
    # 12% on $11,600 to $47,300 = $4,284
    # 22% on remaining $2,700 = $594
    # Total = $6,038
    result = engine.compute_estimated_federal(50000.0)
    expected = (11600 * 0.10) + ((47300 - 11600) * 0.12) + ((50000 - 47300) * 0.22)
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_24_percent_bracket():
    """Test federal tax in higher brackets"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # $100,000 - spans 10%, 12%, 22%, and 24% brackets
    result = engine.compute_estimated_federal(100000.0)
    expected = (11600 * 0.10) + ((47300 - 11600) * 0.12) + ((95375 - 47300) * 0.22) + ((100000 - 95375) * 0.24)
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_top_bracket():
    """Test federal tax in top bracket (37%)"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # $600,000 - spans all brackets including 37%
    result = engine.compute_estimated_federal(600000.0)
    # Calculate expected
    remaining = 600000.0
    tax = 0.0

    # 10% bracket
    bracket_amount = min(remaining, 11600)
    tax += bracket_amount * 0.10
    remaining -= bracket_amount

    # 12% bracket
    if remaining > 0:
        bracket_amount = min(remaining, 47300 - 11600)
        tax += bracket_amount * 0.12
        remaining -= bracket_amount

    # 22% bracket
    if remaining > 0:
        bracket_amount = min(remaining, 95375 - 47300)
        tax += bracket_amount * 0.22
        remaining -= bracket_amount

    # 24% bracket
    if remaining > 0:
        bracket_amount = min(remaining, 182100 - 95375)
        tax += bracket_amount * 0.24
        remaining -= bracket_amount

    # 32% bracket
    if remaining > 0:
        bracket_amount = min(remaining, 231250 - 182100)
        tax += bracket_amount * 0.32
        remaining -= bracket_amount

    # 35% bracket
    if remaining > 0:
        bracket_amount = min(remaining, 578125 - 231250)
        tax += bracket_amount * 0.35
        remaining -= bracket_amount

    # 37% bracket
    if remaining > 0:
        tax += remaining * 0.37

    assert round(result, 2) == round(tax, 2)


def test_get_quarterly_estimate():
    """Test quarterly estimate returns correct structure"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    result = engine.get_quarterly_estimate(100000.0, 2026)

    assert "se_tax" in result
    assert "federal_tax" in result
    assert "total" in result
    assert "due_date" in result
    assert "quarter" in result
    assert "year" in result
    assert result["year"] == 2026
    assert result["quarter"] in ["Q1", "Q2", "Q3", "Q4"]
    assert result["total"] == round(result["se_tax"] + result["federal_tax"], 2)


def test_get_quarterly_estimate_quarter_determination():
    """Test that quarter is determined by current month"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # Mock date.today() to return different months
    with patch('tax_engine.date') as mock_date:
        # Test Q1 (January - March)
        mock_date.today.return_value = date(2026, 2, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q1"
        assert result["due_date"] == "2026-04-15"

        # Test Q2 (April - May)
        mock_date.today.return_value = date(2026, 4, 30)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q2"
        assert result["due_date"] == "2026-06-15"

        # Test Q3 (June - August)
        mock_date.today.return_value = date(2026, 7, 15)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q3"
        assert result["due_date"] == "2026-09-15"

        # Test Q4 (September - December)
        mock_date.today.return_value = date(2026, 10, 15)
        result = engine.get_quarterly_estimate(100000.0, 2026)
        assert result["quarter"] == "Q4"
        assert result["due_date"] == "2027-01-15"


def test_get_irs_deadlines():
    """Test IRS deadlines for a given year"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    deadlines = engine.get_irs_deadlines(2026)

    assert len(deadlines) == 5

    # Check Q1 deadline
    assert deadlines[0]["deadline"] == "2026-04-15"
    assert deadlines[0]["quarter"] == "Q1"
    assert deadlines[0]["description"] == "Q1 Estimated Tax Payment"

    # Check Q2 deadline
    assert deadlines[1]["deadline"] == "2026-06-15"
    assert deadlines[1]["quarter"] == "Q2"

    # Check Q3 deadline
    assert deadlines[2]["deadline"] == "2026-09-15"
    assert deadlines[2]["quarter"] == "Q3"

    # Check Q4 deadline (next year)
    assert deadlines[3]["deadline"] == "2027-01-15"
    assert deadlines[3]["quarter"] == "Q4"

    # Check Annual deadline
    assert deadlines[4]["deadline"] == "2027-04-15"
    assert deadlines[4]["quarter"] == "Annual"
    assert deadlines[4]["description"] == "Annual Tax Return Due"


def test_get_upcoming_alerts():
    """Test upcoming tax alerts within N days"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    # Mock date.today() to a fixed date
    with patch('tax_engine.date') as mock_date:
        mock_date.today.return_value = date(2026, 4, 1)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        # Get alerts for next 30 days (from April 1)
        # Q1 deadline (April 15) is within 30 days
        # Q2 deadline (June 15) is NOT within 30 days
        alerts = engine.get_upcoming_alerts(days_ahead=30)

        # April 15 is within 30 days of April 1
        assert len(alerts) >= 1
        assert any(a["quarter"] == "Q1" for a in alerts)
        assert all(a["days_until"] <= 30 for a in alerts)


def test_get_upcoming_alerts_no_deadlines():
    """Test when no deadlines are within range"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    with patch('tax_engine.date') as mock_date:
        # Set date to just after all deadlines for the year
        mock_date.today.return_value = date(2026, 5, 1)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        # Q1 deadline (April 15) already passed
        # Q2 deadline (June 15) is 45 days away (> 30)
        alerts = engine.get_upcoming_alerts(days_ahead=30)

        # No deadlines within 30 days
        assert len(alerts) == 0


def test_compute_tax_summary():
    """Test tax summary from ledger rows"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

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
    """Test tax summary with empty ledger"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    result = engine.compute_tax_summary([])

    assert result["total_income"] == 0.0
    assert result["total_expenses"] == 0.0
    assert result["net_income"] == 0.0
    assert result["se_tax"] == 0.0
    assert result["federal_tax"] == 0.0
    assert result["total_tax"] == 0.0


def test_compute_tax_summary_invalid_rows():
    """Test tax summary with invalid/malformed rows"""
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)

    ledger_rows = [
        ["2026-01-01", "Client payment", "Services", "Income", "5000.00", "", ""],
        ["short_row"],  # Too short
        ["2026-01-20", "Office", "Office", "Expense", "not_a_number", "", ""],  # Invalid amount
        ["2026-01-21", "Another", "Services", "Income", "", "", ""],  # Empty amount
    ]

    result = engine.compute_tax_summary(ledger_rows)

    # Should handle errors gracefully
    assert result["total_income"] == 5000.0  # Only valid income
    assert result["total_expenses"] == 0.0  # Invalid expense ignored


if __name__ == "__main__":
    pytest.main([__file__])
