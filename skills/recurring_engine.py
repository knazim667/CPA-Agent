from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any


class RecurringEngine:
    def __init__(self, recurring_data: dict[str, Any] | None = None) -> None:
        self._schedules: list[dict[str, Any]] = list((recurring_data or {}).get("schedules", []))

    def get_recurring_data(self) -> dict[str, Any]:
        return {"schedules": [dict(s) for s in self._schedules]}

    def list_schedules(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self._schedules if s.get("active", True)]

    def create_schedule(
        self,
        description: str,
        amount: float,
        category: str,
        entry_type: str,
        frequency: str,
        day_of_period: int,
        start_date: str,
    ) -> dict[str, Any]:
        schedule: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "description": description.strip(),
            "amount": round(float(amount), 2),
            "category": category.strip(),
            "entry_type": entry_type.strip().title(),
            "frequency": frequency.strip().lower(),
            "day_of_period": int(day_of_period),
            "next_date": start_date,
            "active": True,
            "last_posted_date": None,
        }
        self._schedules.append(schedule)
        return schedule

    def cancel_schedule(self, schedule_id: str) -> bool:
        for s in self._schedules:
            if s["id"] == schedule_id:
                s["active"] = False
                return True
        return False

    def update_schedule(self, schedule_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        for s in self._schedules:
            if s["id"] == schedule_id:
                s.update({k: v for k, v in updates.items() if k != "id"})
                return s
        return None

    def run_due_schedules(self, today: str | None = None) -> list[dict[str, Any]]:
        today_str = today or date.today().isoformat()
        due = []
        for s in self._schedules:
            if not s.get("active", True):
                continue
            if s.get("last_posted_date") == today_str:
                continue
            if s.get("next_date", "") <= today_str:
                # Use <= so a schedule missed while the server was offline still posts
                s["last_posted_date"] = today_str
                s["next_date"] = self._advance_date(today_str, s["frequency"], s["day_of_period"])
                due.append(dict(s))
        return due

    @staticmethod
    def _advance_date(from_date: str, frequency: str, day_of_period: int) -> str:
        d = date.fromisoformat(from_date)
        if frequency == "daily":
            return (d + timedelta(days=1)).isoformat()
        if frequency == "weekly":
            return (d + timedelta(weeks=1)).isoformat()
        if frequency == "monthly":
            month = d.month + 1 if d.month < 12 else 1
            year = d.year if d.month < 12 else d.year + 1
            last_day = (date(year, month % 12 + 1, 1) - timedelta(days=1)).day if month != 12 else 31
            return date(year, month, min(day_of_period, last_day)).isoformat()
        if frequency == "annually":
            return date(d.year + 1, d.month, d.day).isoformat()
        return (d + timedelta(days=30)).isoformat()
