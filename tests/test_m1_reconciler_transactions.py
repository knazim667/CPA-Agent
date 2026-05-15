from __future__ import annotations

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from m1_reconciler import M1Draft, M1Reconciler


class MockMemoryManager:
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


def _make_reconciler_with_data(mm=None) -> M1Reconciler:
    if mm is None:
        mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_transaction(1200.0, "meals", 2026)
    rec.record_transaction(500.0, "fines", 2026)
    rec.record_transaction(2400.0, "officer_life_insurance", 2026)
    rec.record_depreciation_difference(8000.0, 12000.0, 2026)
    return rec


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
    rec = M1Reconciler(MockMemoryManager())
    assert rec.record_transaction(100.0, "Meals", 2026) == "meals_50pct"


def test_record_transaction_negative_amount_reduces_total():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_transaction(500.0, "meals", 2026)
    rec.record_transaction(-100.0, "meals", 2026)
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
    rec2 = M1Reconciler(mm)
    summary = rec2.get_ytd_summary(2026)
    assert summary["gaap_depreciation_total"] == 1000.0
    assert summary["macrs_depreciation_total"] == 2000.0


def test_generate_draft_empty_state_line8_equals_line1():
    draft = M1Reconciler(MockMemoryManager()).generate_draft(50000.0, entity_type="s_corp", year=2026)
    assert draft.line1_book_income == 50000.0
    assert draft.line2_federal_tax == 0.0
    assert draft.line5a_meals_disallowed == 0.0
    assert draft.line5b_depreciation_diff == 0.0
    assert draft.line7_other_nondeductible == 0.0
    assert draft.line8_taxable_income == 50000.0


def test_generate_draft_s_corp_correct_math():
    draft = _make_reconciler_with_data().generate_draft(45000.0, entity_type="s_corp", year=2026)
    assert draft.entity_type == "s_corp"
    assert draft.line2_federal_tax == 0.0
    assert draft.line5a_meals_disallowed == pytest.approx(600.0)
    assert draft.line5b_depreciation_diff == pytest.approx(-4000.0)
    assert draft.line7_other_nondeductible == pytest.approx(2900.0)
    assert draft.line8_taxable_income == pytest.approx(44500.0)


def test_generate_draft_c_corp_includes_line2():
    mm = MockMemoryManager()
    rec = M1Reconciler(mm)
    rec.record_transaction(5000.0, "federal_income_tax", 2026)
    draft = rec.generate_draft(45000.0, entity_type="c_corp", year=2026)
    assert draft.entity_type == "c_corp"
    assert draft.line2_federal_tax == 5000.0
    assert draft.line8_taxable_income == pytest.approx(50000.0)


def test_generate_draft_invalid_entity_type_raises():
    with pytest.raises(ValueError, match="entity_type"):
        M1Reconciler(MockMemoryManager()).generate_draft(10000.0, entity_type="partnership", year=2026)


def test_generate_draft_returns_m1draft_instance():
    draft = M1Reconciler(MockMemoryManager()).generate_draft(10000.0, year=2026)
    assert isinstance(draft, M1Draft)
    assert draft.year == 2026
    assert isinstance(draft.formatted, str)
    assert len(draft.formatted) > 0


def test_generate_draft_formatted_contains_line_labels():
    draft = _make_reconciler_with_data().generate_draft(45000.0, entity_type="s_corp", year=2026)
    assert "Line 1" in draft.formatted
    assert "Line 5a" in draft.formatted
    assert "Line 5b" in draft.formatted
    assert "Line 7" in draft.formatted
    assert "Line 8" in draft.formatted
    assert "Line 2" not in draft.formatted


def test_generate_draft_c_corp_formatted_includes_line2():
    draft = M1Reconciler(MockMemoryManager()).generate_draft(10000.0, entity_type="c_corp", year=2026)
    assert "Line 2" in draft.formatted
