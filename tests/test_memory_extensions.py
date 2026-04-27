import json, pytest
from pathlib import Path
from memory_manager import MemoryManager

@pytest.fixture
def mgr(tmp_path):
    # Create a minimal business profile so MemoryManager can boot
    biz_dir = tmp_path / "long_term" / "test_biz"
    biz_dir.mkdir(parents=True)
    (biz_dir / "config.json").write_text(json.dumps({
        "business_name": "Test Biz",
        "google_sheet_id": "x", "google_doc_id": "x",
        "local_memory_db": "", "federal_ein": "", "state": "", "default_books_currency": "USD"
    }))
    (tmp_path / "active_business.json").write_text(json.dumps({"active_business": "test_biz"}))
    return MemoryManager(tmp_path)

def test_load_category_rules_returns_empty_on_new_business(mgr):
    data = mgr.load_category_rules()
    assert data == {"rules": []}

def test_save_and_reload_category_rules(mgr):
    mgr.save_category_rules({"rules": [{"id": "1", "pattern": "aws", "category": "Cloud"}]})
    data = mgr.load_category_rules()
    assert data["rules"][0]["category"] == "Cloud"

def test_load_recurring_returns_empty_on_new_business(mgr):
    data = mgr.load_recurring()
    assert data == {"schedules": []}

def test_save_and_reload_recurring(mgr):
    mgr.save_recurring({"schedules": [{"id": "1", "description": "Rent", "amount": 2000}]})
    data = mgr.load_recurring()
    assert data["schedules"][0]["description"] == "Rent"
