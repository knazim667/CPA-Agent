import pytest
from datetime import date
from skills.recurring_engine import RecurringEngine

def make_engine(schedules=None):
    data = {"schedules": schedules or []}
    return RecurringEngine(recurring_data=data)

def test_create_schedule_adds_entry():
    engine = make_engine()
    s = engine.create_schedule(
        description="Rent", amount=2000.0, category="Rent",
        entry_type="Expense", frequency="monthly",
        day_of_period=1, start_date="2026-05-01"
    )
    assert s["description"] == "Rent"
    assert s["next_date"] == "2026-05-01"
    assert s["active"] is True

def test_cancel_schedule_sets_inactive():
    engine = make_engine([{
        "id": "abc", "description": "Rent", "amount": 2000, "category": "Rent",
        "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
        "next_date": "2026-05-01", "active": True, "last_posted_date": None
    }])
    result = engine.cancel_schedule("abc")
    assert result is True
    assert engine._schedules[0]["active"] is False
    assert engine.list_schedules() == []

def test_run_due_schedules_returns_due_entry():
    today = "2026-05-01"
    engine = make_engine([{
        "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
        "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
        "next_date": today, "active": True, "last_posted_date": None
    }])
    due = engine.run_due_schedules(today=today)
    assert len(due) == 1
    assert due[0]["description"] == "Rent"

def test_run_due_schedules_advances_next_date():
    today = "2026-05-01"
    engine = make_engine([{
        "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
        "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
        "next_date": today, "active": True, "last_posted_date": None
    }])
    engine.run_due_schedules(today=today)
    schedule = engine.list_schedules()[0]
    assert schedule["next_date"] == "2026-06-01"
    assert schedule["last_posted_date"] == today

def test_run_due_schedules_is_idempotent():
    today = "2026-05-01"
    engine = make_engine([{
        "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
        "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
        "next_date": today, "active": True, "last_posted_date": today
    }])
    due = engine.run_due_schedules(today=today)
    assert len(due) == 0  # already posted today

def test_run_due_schedules_skips_inactive():
    today = "2026-05-01"
    engine = make_engine([{
        "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
        "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
        "next_date": today, "active": False, "last_posted_date": None
    }])
    due = engine.run_due_schedules(today=today)
    assert len(due) == 0
