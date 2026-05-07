from __future__ import annotations

import dataclasses
import json
import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from memory_manager import MemoryManager
from m1_reconciler import (
    M1Draft,
    M1Reconciler,
    VALID_ADJUSTMENT_TYPES,
    _DEFAULT_CATEGORY_MAP,
    _ZERO_YEAR_STATE,
)


@pytest.fixture
def mm_with_business(tmp_path):
    """Create a MemoryManager with a test business profile."""
    business_dir = tmp_path / "long_term" / "test_biz"
    business_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "business_name": "Test Business",
        "federal_ein": "",
        "state": "",
        "default_books_currency": "USD"
    }
    (business_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    (tmp_path / "active_business.json").write_text(
        json.dumps({"active_business": "test_biz"}), encoding="utf-8"
    )

    mm = MemoryManager(tmp_path)
    return mm


def test_memory_manager_load_m1_state_returns_empty_dict_when_missing(mm_with_business):
    result = mm_with_business.load_m1_state()
    assert result == {}


def test_memory_manager_save_and_load_m1_state_roundtrip(mm_with_business):
    data = {"2026": {"meals_total": 1200.0, "fines_total": 0.0}}
    mm_with_business.save_m1_state(data)
    loaded = mm_with_business.load_m1_state()
    assert loaded == data


def test_memory_manager_load_m1_category_map_returns_empty_dict_when_missing(mm_with_business):
    result = mm_with_business.load_m1_category_map()
    assert result == {}


def test_memory_manager_save_and_load_m1_category_map_roundtrip(mm_with_business):
    data = {"club_dues": "other_nondeductible"}
    mm_with_business.save_m1_category_map(data)
    loaded = mm_with_business.load_m1_category_map()
    assert loaded == data


class MockMemoryManager:
    """In-memory stand-in for MemoryManager used across all M-1 tests."""
    def __init__(self):
        self._m1_state: dict = {}
        self._m1_map: dict = {}

    def load_m1_state(self) -> dict:
        return dict(self._m1_state)

    def save_m1_state(self, data: dict) -> None:
        self._m1_state = dict(data)

    def load_m1_category_map(self) -> dict:
        return dict(self._m1_map)

    def save_m1_category_map(self, data: dict) -> None:
        self._m1_map = dict(data)


def test_valid_adjustment_types_contains_expected():
    assert "meals_50pct" in VALID_ADJUSTMENT_TYPES
    assert "fines" in VALID_ADJUSTMENT_TYPES
    assert "officer_life_insurance" in VALID_ADJUSTMENT_TYPES
    assert "federal_income_tax" in VALID_ADJUSTMENT_TYPES
    assert "other_nondeductible" in VALID_ADJUSTMENT_TYPES
    assert len(VALID_ADJUSTMENT_TYPES) == 5


def test_default_category_map_meals():
    assert _DEFAULT_CATEGORY_MAP["meals"] == "meals_50pct"
    assert _DEFAULT_CATEGORY_MAP["entertainment"] == "meals_50pct"


def test_default_category_map_fines():
    assert _DEFAULT_CATEGORY_MAP["fines"] == "fines"
    assert _DEFAULT_CATEGORY_MAP["penalties"] == "fines"


def test_m1draft_fields():
    draft = M1Draft(
        year=2026,
        entity_type="s_corp",
        line1_book_income=45000.0,
        line2_federal_tax=0.0,
        line5a_meals_disallowed=600.0,
        line5b_depreciation_diff=-4000.0,
        line7_other_nondeductible=2900.0,
        line8_taxable_income=44500.0,
        formatted="test",
    )
    assert draft.year == 2026
    assert draft.entity_type == "s_corp"
    assert draft.line1_book_income == 45000.0
    assert draft.line2_federal_tax == 0.0
    assert draft.line5a_meals_disallowed == 600.0
    assert draft.line5b_depreciation_diff == -4000.0
    assert draft.line7_other_nondeductible == 2900.0
    assert draft.line8_taxable_income == 44500.0
    assert draft.formatted == "test"
    assert len(dataclasses.fields(M1Draft)) == 9


def test_m1_reconciler_initialises_from_empty_memory():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    assert rec._state == {}
    assert rec._custom_map == {}


def test_add_category_mapping_accepts_valid_type():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.add_category_mapping("club_dues", "other_nondeductible")
    assert rec._custom_map["club_dues"] == "other_nondeductible"
    assert mm._m1_map["club_dues"] == "other_nondeductible"


def test_add_category_mapping_rejects_invalid_type():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    with pytest.raises(ValueError, match="Invalid adjustment_type"):
        rec.add_category_mapping("club_dues", "not_a_real_type")


def test_add_category_mapping_normalises_category_to_lowercase():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.add_category_mapping("Club Dues", "other_nondeductible")
    assert "club dues" in mm._m1_map


def test_get_ytd_summary_returns_zeros_for_unknown_year():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    summary = rec.get_ytd_summary(2026)
    assert summary["meals_total"] == 0.0
    assert summary["gaap_depreciation_total"] == 0.0
    assert set(summary.keys()) == set(_ZERO_YEAR_STATE.keys())
    assert rec._state == {}  # unknown year must not pollute state


def test_get_ytd_summary_returns_recorded_totals():
    mm = MockMemoryManager()
    mm._m1_state = {"2026": {**_ZERO_YEAR_STATE, "meals_total": 1200.0}}
    rec = M1Reconciler(mm)
    summary = rec.get_ytd_summary(2026)
    assert summary["meals_total"] == 1200.0


def test_record_transaction_default_meals_mapping():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    result = rec.record_transaction(1200.0, "meals", 2026)
    assert result == "meals_50pct"
    assert mm._m1_state["2026"]["meals_total"] == 1200.0


def test_record_transaction_unknown_category_returns_none():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    result = rec.record_transaction(500.0, "office_supplies", 2026)
    assert result is None
    assert "2026" not in mm._m1_state


def test_record_transaction_accumulates_across_calls():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_transaction(300.0, "meals", 2026)
    rec.record_transaction(400.0, "entertainment", 2026)
    assert mm._m1_state["2026"]["meals_total"] == pytest.approx(700.0)


def test_record_transaction_fines_uses_correct_field():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_transaction(500.0, "fines", 2026)
    assert mm._m1_state["2026"]["fines_total"] == 500.0


def test_record_transaction_custom_mapping_takes_precedence():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.add_category_mapping("club_dues", "other_nondeductible")
    result = rec.record_transaction(800.0, "club_dues", 2026)
    assert result == "other_nondeductible"
    assert mm._m1_state["2026"]["other_nondeductible_total"] == 800.0


def test_record_transaction_case_insensitive_category():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    result = rec.record_transaction(100.0, "Meals", 2026)
    assert result == "meals_50pct"


def test_record_transaction_negative_amount_reduces_total():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_transaction(500.0, "meals", 2026)
    rec.record_transaction(-100.0, "meals", 2026)  # refund
    assert mm._m1_state["2026"]["meals_total"] == pytest.approx(400.0)


def test_record_depreciation_difference_stores_both_totals():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_depreciation_difference(8000.0, 12000.0, 2026)
    state = mm._m1_state["2026"]
    assert state["gaap_depreciation_total"] == 8000.0
    assert state["macrs_depreciation_total"] == 12000.0


def test_record_depreciation_difference_accumulates():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_depreciation_difference(5000.0, 8000.0, 2026)
    rec.record_depreciation_difference(3000.0, 4000.0, 2026)
    state = mm._m1_state["2026"]
    assert state["gaap_depreciation_total"] == pytest.approx(8000.0)
    assert state["macrs_depreciation_total"] == pytest.approx(12000.0)


def test_record_depreciation_difference_persists_state():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_depreciation_difference(1000.0, 2000.0, 2026)
    # Simulate reload from persistence
    rec2 = M1Reconciler(mm)
    summary = rec2.get_ytd_summary(2026)
    assert summary["gaap_depreciation_total"] == 1000.0
    assert summary["macrs_depreciation_total"] == 2000.0
