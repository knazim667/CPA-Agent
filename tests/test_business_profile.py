from __future__ import annotations
import json
import tempfile
from pathlib import Path
import pytest
from memory_manager import MemoryManager, PROFILE_DEFAULTS


@pytest.fixture()
def mm(tmp_path):
    # Seed with a minimal existing business to satisfy _discover_business_keys
    biz_dir = tmp_path / "long_term" / "old_biz"
    biz_dir.mkdir(parents=True)
    (biz_dir / "config.json").write_text(json.dumps({
        "business_name": "Old Biz",
        "google_sheet_id": "",
        "google_doc_id": "",
        "local_memory_db": "",
        "federal_ein": "",
        "state": "",
        "default_books_currency": "USD",
    }), encoding="utf-8")
    (tmp_path / "active_business.json").write_text(
        json.dumps({"active_business": "old_biz"}), encoding="utf-8"
    )
    return MemoryManager(tmp_path)


def test_profile_defaults_exported():
    assert "legal_structure" in PROFILE_DEFAULTS
    assert "industry" in PROFILE_DEFAULTS
    assert "onboarding_complete" in PROFILE_DEFAULTS


def test_create_business_includes_new_fields(mm):
    key, profile, _ = mm.create_business("New Co")
    assert "legal_structure" in profile
    assert "industry" in profile
    assert "onboarding_complete" in profile
    assert profile["onboarding_complete"] is False


def test_migrate_adds_missing_fields(mm):
    mm.migrate_business_profiles()
    profile = mm.load_business_profile("old_biz")
    assert "legal_structure" in profile
    assert "onboarding_complete" in profile
    assert profile["onboarding_complete"] is False


def test_migrate_does_not_overwrite_existing_fields(mm):
    mm.migrate_business_profiles()
    # Run again — should be idempotent
    mm.migrate_business_profiles()
    profile = mm.load_business_profile("old_biz")
    assert profile["business_name"] == "Old Biz"


def test_update_business_profile_partial(mm):
    mm.migrate_business_profiles()
    updated = mm.update_business_profile("old_biz", {"industry": "retail", "accounting_basis": "accrual"})
    assert updated["industry"] == "retail"
    assert updated["accounting_basis"] == "accrual"
    assert updated["business_name"] == "Old Biz"  # unchanged


def test_create_business_defaults_are_not_aliased(mm):
    _, p1, _ = mm.create_business("Biz One")
    _, p2, _ = mm.create_business("Biz Two")
    p1["operating_states"].append("CA")
    assert "CA" not in p2["operating_states"]
    assert "CA" not in PROFILE_DEFAULTS["operating_states"]
