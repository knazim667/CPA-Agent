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
