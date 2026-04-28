from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import os
from skills.reconciliation_engine import ReconciliationEngine

# Ledger row schema: [Date, Description, Category, Amount, Type, Reference, Notes]
LEDGER_ROWS = [
    ["2026-05-01", "Starbucks", "Meals", "45.00", "Expense", "", ""],
    ["2026-05-05", "Client invoice", "Sales", "3000.00", "Income", "", ""],
    ["2026-05-10", "Facebook Ads", "Marketing", "400.00", "Expense", "", ""],
    ["2026-05-15", "Google Ads", "Marketing", "350.00", "Expense", "", ""],
    ["2026-05-20", "AWS", "Software", "89.00", "Expense", "", ""],
]

BANK_TRANSACTIONS_CSV = """Date,Description,Amount
2026-05-01,Starbucks Coffee,-45.00
2026-05-05,Client Payment,3000.00
2026-05-10,Facebook Advertising,-400.00
2026-05-15,Google Ads,-350.00
2026-05-20,Amazon Web Services,-89.00
"""

BANK_TRANSACTIONS_WITH_DIFFERENCES_CSV = """Date,Description,Amount
2026-05-01,Starbucks Coffee,-45.00
2026-05-05,Client Payment,3000.00
2026-05-10,Facebook Advertising,-400.00
2026-05-16,Google Ads,-350.00  # One day off
2026-05-20,AWS Cloud Services,-90.00  # Slightly different amount
2026-05-25,Bank Fee,-25.00  # Not in ledger
"""


def create_temp_csv(content: str) -> Path:
    """Create a temporary CSV file with the given content."""
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    temp_file.write(content)
    temp_file.close()
    return Path(temp_file.name)


def test_parse_bank_statement_csv():
    """Test parsing a CSV bank statement."""
    engine = ReconciliationEngine()
    temp_file = create_temp_csv(BANK_TRANSACTIONS_CSV)

    try:
        transactions = engine.parse_bank_statement(temp_file)

        assert len(transactions) == 5
        # Check first transaction
        assert transactions[0]['date'] == '2026-05-01'
        assert transactions[0]['description'] == 'Starbucks Coffee'
        assert transactions[0]['amount'] == -45.0
        # Check last transaction
        assert transactions[4]['date'] == '2026-05-20'
        assert transactions[4]['description'] == 'Amazon Web Services'
        assert transactions[4]['amount'] == -89.0
    finally:
        os.unlink(temp_file)


def test_parse_bank_statement_unsupported_format():
    """Test parsing an unsupported file format."""
    engine = ReconciliationEngine()
    temp_file = create_temp_csv("dummy,data")
    temp_file = temp_file.with_suffix('.txt')  # Change extension

    try:
        with pytest.raises(ValueError, match="Unsupported file format"):
            engine.parse_bank_statement(temp_file)
    finally:
        if temp_file.exists():
            os.unlink(temp_file)


def test_match_transactions_perfect_match():
    """Test matching transactions with perfect alignment."""
    engine = ReconciliationEngine()
    temp_file = create_temp_csv(BANK_TRANSACTIONS_CSV)

    try:
        bank_rows = engine._parse_csv(temp_file)
        result = engine.match_transactions(bank_rows, LEDGER_ROWS)

        # All should match perfectly
        assert len(result['matched']) == 5
        assert len(result['unmatched_bank']) == 0
        assert len(result['unmatched_ledger']) == 0

        # Check a specific match
        starbucks_match = next(m for m in result['matched']
                              if m['bank']['description'] == 'Starbucks Coffee')
        assert starbucks_match['ledger'][1] == "Starbucks"  # Description
        assert abs(float(starbucks_match['ledger'][3].replace('$', '').replace(',', '')) - 45.0) < 0.01  # Amount
    finally:
        os.unlink(temp_file)


def test_match_transactions_with_date_tolerance():
    """Test matching transactions with date tolerance."""
    engine = ReconciliationEngine()
    temp_file = create_temp_csv(BANK_TRANSACTIONS_WITH_DIFFERENCES_CSV)

    try:
        bank_rows = engine._parse_csv(temp_file)
        # With tolerance of 1 day:
        # - Google Ads (2026-05-16) matches ledger Google Ads (2026-05-15) with 1 day tolerance
        # - Starbucks, Client Payment, Facebook Advertising match exactly
        # - AWS Cloud Services unmatched due to amount mismatch (-90 vs -89)
        # - Bank Fee unmatched (not in ledger)
        # - AWS ledger transaction unmatched (no matching bank transaction due to amount mismatch)
        result = engine.match_transactions(bank_rows, LEDGER_ROWS, tolerance_days=1)

        # Should match 4 out of 6 transactions (4 bank, 5 ledger)
        assert len(result['matched']) == 4
        assert len(result['unmatched_bank']) == 2  # AWS Cloud Services and Bank Fee
        assert len(result['unmatched_ledger']) == 1  # AWS ledger transaction

        # Check that bank fee is unmatched
        bank_fee_unmatched = any(tx['description'] == 'Bank Fee' for tx in result['unmatched_bank'])
        assert bank_fee_unmatched

        # Check that AWS ledger transaction is unmatched
        aws_ledger_unmatched = any('AWS' in str(tx[1]) and tx[4] == 'Expense' for tx in result['unmatched_ledger'])
        assert aws_ledger_unmatched
    finally:
        if temp_file.exists():
            os.unlink(temp_file)


def test_match_transactions_amount_mismatch():
    """Test that amount mismatches prevent matching."""
    engine = ReconciliationEngine()
    temp_file = create_temp_csv(BANK_TRANSACTIONS_WITH_DIFFERENCES_CSV)

    try:
        bank_rows = engine._parse_csv(temp_file)
        # With zero tolerance for amount differences, AWS should not match
        result = engine.match_transactions(bank_rows, LEDGER_ROWS, tolerance_days=1)

        # AWS transaction should be unmatched due to amount difference (89 vs 90)
        aws_unmatched = any('AWS' in tx['description'] for tx in result['unmatched_bank'])
        assert aws_unmatched
    finally:
        os.unlink(temp_file)


def test_match_transactions_empty_inputs():
    """Test matching with empty inputs."""
    engine = ReconciliationEngine()

    result = engine.match_transactions([], [])

    assert len(result['matched']) == 0
    assert len(result['unmatched_bank']) == 0
    assert len(result['unmatched_ledger']) == 0


def test_compute_difference():
    """Test computing the difference between bank and ledger balances."""
    engine = ReconciliationEngine()

    # Bank balance higher than ledger
    diff = engine.compute_difference(1000.0, 800.0)
    assert diff == 200.0

    # Ledger balance higher than bank
    diff = engine.compute_difference(800.0, 1000.0)
    assert diff == -200.0

    # Equal balances
    diff = engine.compute_difference(500.0, 500.0)
    assert diff == 0.0