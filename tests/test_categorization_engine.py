import pytest
from skills.categorization_engine import CategorizationEngine

RULES = {
    "rules": [
        {"id": "r1", "pattern": "starbucks", "match_type": "contains",
         "category": "Meals & Entertainment", "confidence": 0.95, "use_count": 10},
        {"id": "r2", "pattern": "aws", "match_type": "contains",
         "category": "Cloud Infra", "confidence": 0.9, "use_count": 5},
    ]
}

def test_suggest_returns_match_for_known_vendor():
    engine = CategorizationEngine(rules_data=RULES)
    result = engine.suggest_category("Starbucks #4421")
    assert result is not None
    assert result["category"] == "Meals & Entertainment"
    assert result["confidence"] == 0.95

def test_suggest_returns_none_for_unknown_vendor():
    engine = CategorizationEngine(rules_data=RULES)
    assert engine.suggest_category("Random New Vendor XYZ") is None

def test_suggest_is_case_insensitive():
    engine = CategorizationEngine(rules_data=RULES)
    result = engine.suggest_category("AMAZON WEB SERVICES AWS")
    assert result is not None
    assert result["category"] == "Cloud Infra"

def test_save_rule_adds_new_rule():
    engine = CategorizationEngine(rules_data={"rules": []})
    engine.save_rule("Office Depot", "Office Supplies")
    result = engine.suggest_category("Office Depot purchase")
    assert result is not None
    assert result["category"] == "Office Supplies"

def test_save_rule_updates_existing_rule():
    engine = CategorizationEngine(rules_data=RULES)
    engine.save_rule("starbucks", "Coffee")  # override
    result = engine.suggest_category("Starbucks #111")
    assert result["category"] == "Coffee"

def test_backfill_creates_rules_for_repeated_pairs():
    engine = CategorizationEngine(rules_data={"rules": []})
    rows = [
        ["2026-01-01", "Starbucks", "Meals", "10", "Expense", "", ""],
        ["2026-01-02", "Starbucks", "Meals", "8",  "Expense", "", ""],
        ["2026-01-03", "AWS",       "Cloud", "89", "Expense", "", ""],
        ["2026-01-04", "AWS",       "Cloud", "89", "Expense", "", ""],
        ["2026-01-05", "OneTime",   "Misc",  "50", "Expense", "", ""],
    ]
    count = engine.backfill_rules_from_ledger(rows)
    assert count == 2  # Starbucks+AWS had >=2 occurrences; OneTime did not
    assert engine.suggest_category("Starbucks latte") is not None
    assert engine.suggest_category("AWS bill") is not None
    assert engine.suggest_category("OneTime payment") is None


# ── split_transaction ──────────────────────────────────────────────────────


def _two_splits() -> tuple[float, list[dict]]:
    return 200.0, [
        {"amount": 100.0, "category": "Office Supplies", "description": "Amazon - office supplies"},
        {"amount": 100.0, "category": "Inventory", "description": "Amazon - inventory"},
    ]


def _three_splits() -> tuple[float, list[dict]]:
    return 300.0, [
        {"amount": 150.0, "category": "Office Supplies", "description": "Amazon - office supplies"},
        {"amount": 100.0, "category": "Equipment", "description": "Amazon - equipment"},
        {"amount":  50.0, "category": "Meals & Entertainment", "description": "Amazon - meals"},
    ]


def test_split_transaction_returns_correct_row_count():
    engine = CategorizationEngine()
    total, splits = _two_splits()
    rows = engine.split_transaction(total, splits, date="2026-05-07")
    assert len(rows) == 2


def test_split_transaction_row_structure():
    engine = CategorizationEngine()
    total, splits = _two_splits()
    rows = engine.split_transaction(total, splits, date="2026-05-07")
    row = rows[0]
    assert len(row) == 7
    assert row[0] == "2026-05-07"                   # date
    assert row[1] == "Amazon - office supplies"     # description
    assert row[2] == "Office Supplies"              # category
    assert row[3] == 100.0                          # amount
    assert row[4] == "Expense"                      # entry_type default
    assert row[5] == ""                             # reference empty
    assert row[6] == "split 1/2"                   # notes


def test_split_transaction_split_note_format():
    engine = CategorizationEngine()
    total, splits = _three_splits()
    rows = engine.split_transaction(total, splits, date="2026-05-07")
    assert rows[0][6] == "split 1/3"
    assert rows[1][6] == "split 2/3"
    assert rows[2][6] == "split 3/3"


def test_split_transaction_raises_on_empty_splits():
    engine = CategorizationEngine()
    with pytest.raises(ValueError, match="at least one split"):
        engine.split_transaction(100.0, [])


def test_split_transaction_raises_on_amount_mismatch():
    engine = CategorizationEngine()
    splits = [
        {"amount": 60.0, "category": "Office Supplies", "description": "Amazon - supplies"},
        {"amount": 60.0, "category": "Inventory",       "description": "Amazon - inventory"},
    ]
    with pytest.raises(ValueError, match="do not match total"):
        engine.split_transaction(100.0, splits)


def test_split_transaction_raises_on_missing_key():
    engine = CategorizationEngine()
    splits = [{"amount": 100.0, "category": "Office Supplies"}]  # missing description
    with pytest.raises(ValueError, match="description"):
        engine.split_transaction(100.0, splits)


def test_split_transaction_single_split():
    engine = CategorizationEngine()
    splits = [{"amount": 50.0, "category": "Meals & Entertainment", "description": "Starbucks - coffee"}]
    rows = engine.split_transaction(50.0, splits, date="2026-05-07")
    assert len(rows) == 1
    assert rows[0][6] == "split 1/1"


def test_split_transaction_raises_on_non_numeric_amount():
    engine = CategorizationEngine()
    splits = [{"amount": "100.00", "category": "Office Supplies", "description": "Amazon - supplies"}]
    with pytest.raises(ValueError, match="must be a number"):
        engine.split_transaction(100.0, splits)


def test_split_transaction_custom_entry_type():
    engine = CategorizationEngine()
    splits = [{"amount": 500.0, "category": "Sales Revenue", "description": "Client payment"}]
    rows = engine.split_transaction(500.0, splits, date="2026-05-07", entry_type="Income")
    assert rows[0][4] == "Income"


def test_split_transaction_default_date_is_empty_string():
    engine = CategorizationEngine()
    splits = [{"amount": 50.0, "category": "Office", "description": "Pen"}]
    rows = engine.split_transaction(50.0, splits)  # no date kwarg
    assert rows[0][0] == ""
