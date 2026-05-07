from __future__ import annotations

import json
import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from memory_manager import MemoryManager


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
