import pytest
from unittest.mock import Mock, patch
from datetime import date, timedelta
from pathlib import Path
import sys
import os

# Add the skills directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from ar_ap_engine import ARAPEngine


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


def test_arap_engine_initialization():
    """Test that ARAPEngine initializes correctly"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    assert engine.memory == mock_memory
    assert engine.file_path.name == "ar_ap.json"


def test_add_receivable():
    """Test adding a receivable entry"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    # Mock the file operations
    with patch.object(engine, '_load_data', return_value={"receivables": [], "payables": []}):
        with patch.object(engine, '_save_data'):
            result = engine.add_receivable(
                client="Test Client",
                amount=1000.00,
                due_date="2026-05-30",
                notes="Test receivable"
            )

    assert result["client_vendor"] == "Test Client"
    assert result["amount"] == 1000.00
    assert result["due_date"] == "2026-05-30"
    assert result["status"] == "open"
    assert result["notes"] == "Test receivable"
    assert result["entry_type"] == "receivable"
    assert "id" in result


def test_add_payable():
    """Test adding a payable entry"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    # Mock the file operations
    with patch.object(engine, '_load_data', return_value={"receivables": [], "payables": []}):
        with patch.object(engine, '_save_data'):
            result = engine.add_payable(
                vendor="Test Vendor",
                amount=500.00,
                due_date="2026-06-15",
                notes="Test payable"
            )

    assert result["client_vendor"] == "Test Vendor"
    assert result["amount"] == 500.00
    assert result["due_date"] == "2026-06-15"
    assert result["status"] == "open"
    assert result["notes"] == "Test payable"
    assert result["entry_type"] == "payable"
    assert "id" in result


def test_mark_paid():
    """Test marking an entry as paid"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    # Mock the file operations
    test_entry = {
        "id": "test-id",
        "client_vendor": "Test Client",
        "amount": 1000.00,
        "due_date": "2026-05-30",
        "issue_date": "2026-05-01",
        "status": "open",
        "notes": "Test entry",
        "entry_type": "receivable"
    }

    with patch.object(engine, '_load_data', return_value={"receivables": [test_entry], "payables": []}):
        with patch.object(engine, '_save_data'):
            result = engine.mark_paid(
                entry_id="test-id",
                entry_type="receivable",
                paid_date="2026-05-15"
            )

    assert result["status"] == "paid"


def test_get_ar_ap():
    """Test getting AR/AP data"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    test_data = {
        "receivables": [
            {
                "id": "1",
                "client_vendor": "Client 1",
                "amount": 1000.00,
                "due_date": "2026-05-30",
                "issue_date": "2026-05-01",
                "status": "open",
                "notes": "Test",
                "entry_type": "receivable"
            }
        ],
        "payables": [
            {
                "id": "2",
                "client_vendor": "Vendor 1",
                "amount": 500.00,
                "due_date": "2026-06-15",
                "issue_date": "2026-05-01",
                "status": "open",
                "notes": "Test",
                "entry_type": "payable"
            }
        ]
    }

    with patch.object(engine, '_load_data', return_value=test_data):
        result = engine.get_ar_ap()

        assert len(result["receivables"]) == 1
        assert len(result["payables"]) == 1
        assert result["receivables"][0]["client_vendor"] == "Client 1"
        assert result["payables"][0]["client_vendor"] == "Vendor 1"


def test_get_overdue_items():
    """Test getting overdue items"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    # Set up test data with overdue items
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last_month = (date.today() - timedelta(days=45)).isoformat()

    test_data = {
        "receivables": [
            {
                "id": "1",
                "client_vendor": "Overdue Client",
                "amount": 1000.00,
                "due_date": yesterday,  # Yesterday - overdue
                "issue_date": "2026-04-01",
                "status": "open",
                "notes": "Overdue receivable",
                "entry_type": "receivable"
            },
            {
                "id": "2",
                "client_vendor": "Current Client",
                "amount": 500.00,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),  # Future - not overdue
                "issue_date": "2026-05-01",
                "status": "open",
                "notes": "Current receivable",
                "entry_type": "receivable"
            }
        ],
        "payables": [
            {
                "id": "3",
                "client_vendor": "Overdue Vendor",
                "amount": 2000.00,
                "due_date": last_month,  # Last month - overdue
                "issue_date": "2026-04-01",
                "status": "open",
                "notes": "Overdue payable",
                "entry_type": "payable"
            }
        ]
    }

    with patch.object(engine, '_load_data', return_value=test_data):
        result = engine.get_overdue_items()

        assert len(result["receivables"]) == 1
        assert len(result["payables"]) == 1
        assert result["receivables"][0]["client_vendor"] == "Overdue Client"
        assert result["payables"][0]["client_vendor"] == "Overdue Vendor"


def test_get_upcoming_due():
    """Test getting upcoming due items"""
    mock_memory = MockMemoryManager()
    engine = ARAPEngine(mock_memory)

    # Set up test data
    today = date.today()
    soon = (today + timedelta(days=5)).isoformat()  # Within 7 days
    later = (today + timedelta(days=30)).isoformat()  # Beyond 7 days

    test_data = {
        "receivables": [
            {
                "id": "1",
                "client_vendor": "Soon Client",
                "amount": 1000.00,
                "due_date": soon,  # Within 7 days
                "issue_date": "2026-05-01",
                "status": "open",
                "notes": "Soon receivable",
                "entry_type": "receivable"
            },
            {
                "id": "2",
                "client_vendor": "Later Client",
                "amount": 500.00,
                "due_date": later,  # Beyond 7 days
                "issue_date": "2026-05-01",
                "status": "open",
                "notes": "Later receivable",
                "entry_type": "receivable"
            }
        ],
        "payables": []
    }

    with patch.object(engine, '_load_data', return_value=test_data):
        result = engine.get_upcoming_due(days_ahead=7)

        assert len(result["receivables"]) == 1
        assert len(result["payables"]) == 0
        assert result["receivables"][0]["client_vendor"] == "Soon Client"


if __name__ == "__main__":
    pytest.main([__file__])