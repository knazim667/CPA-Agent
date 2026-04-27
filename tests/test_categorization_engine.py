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
