import pytest
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


def test_tax_engine_initialization():
    mock_memory = MockMemoryManager()
    engine = TaxEngine(mock_memory)
    assert engine.memory == mock_memory


def test_compute_se_tax_zero_income():
    engine = TaxEngine(MockMemoryManager())
    assert engine.compute_se_tax(0.0) == 0.0
    assert engine.compute_se_tax(-1000.0) == 0.0


def test_compute_se_tax_positive_income():
    engine = TaxEngine(MockMemoryManager())
    result = engine.compute_se_tax(100000.0)
    expected = 100000.0 * 0.9235 * 0.153
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_zero_income():
    assert TaxEngine(MockMemoryManager()).compute_estimated_federal(0.0) == 0.0


def test_compute_estimated_federal_10_percent_bracket():
    result = TaxEngine(MockMemoryManager()).compute_estimated_federal(5000.0)
    assert round(result, 2) == round(5000.0 * 0.10, 2)


def test_compute_estimated_federal_12_percent_bracket():
    result = TaxEngine(MockMemoryManager()).compute_estimated_federal(15000.0)
    expected = (11600 * 0.10) + ((15000 - 11600) * 0.12)
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_22_percent_bracket():
    result = TaxEngine(MockMemoryManager()).compute_estimated_federal(50000.0)
    expected = (11600 * 0.10) + ((47300 - 11600) * 0.12) + ((50000 - 47300) * 0.22)
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_24_percent_bracket():
    result = TaxEngine(MockMemoryManager()).compute_estimated_federal(100000.0)
    expected = (
        (11600 * 0.10)
        + ((47300 - 11600) * 0.12)
        + ((95375 - 47300) * 0.22)
        + ((100000 - 95375) * 0.24)
    )
    assert round(result, 2) == round(expected, 2)


def test_compute_estimated_federal_top_bracket():
    result = TaxEngine(MockMemoryManager()).compute_estimated_federal(600000.0)
    remaining = 600000.0
    tax = 0.0
    brackets = [
        (11600, 0.10),
        (47300 - 11600, 0.12),
        (95375 - 47300, 0.22),
        (182100 - 95375, 0.24),
        (231250 - 182100, 0.32),
        (578125 - 231250, 0.35),
    ]
    for cap, rate in brackets:
        amount = min(remaining, cap)
        tax += amount * rate
        remaining -= amount
    if remaining > 0:
        tax += remaining * 0.37
    assert round(result, 2) == round(tax, 2)


if __name__ == "__main__":
    pytest.main([__file__])
