from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import uuid


@dataclass
class ARAPEntry:
    id: str
    client_vendor: str
    amount: float
    due_date: str  # YYYY-MM-DD
    issue_date: str  # YYYY-MM-DD
    status: str  # open/paid/overdue
    notes: str
    entry_type: str  # receivable/payable
    days_outstanding: int = 0
    age_bucket: str = "current"  # current/30/60/90


class ARAPEngine:
    def __init__(self, memory_manager):
        self.memory = memory_manager
        self.file_path = self.memory.long_term_dir / self.memory.current_business_key / "ar_ap.json"

    def _load_data(self) -> Dict[str, List[Dict]]:
        if not self.file_path.exists():
            return {"receivables": [], "payables": []}
        with self.file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_data(self, data: Dict[str, List[Dict]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _calculate_aging(self, entries: List[Dict]) -> List[Dict]:
        today = datetime.now().date()
        for entry in entries:
            due_date = datetime.strptime(entry["due_date"], "%Y-%m-%d").date()
            days_outstanding = (today - due_date).days
            entry["days_outstanding"] = days_outstanding

            if days_outstanding <= 0:
                entry["age_bucket"] = "current"
            elif days_outstanding <= 30:
                entry["age_bucket"] = "30"
            elif days_outstanding <= 60:
                entry["age_bucket"] = "60"
            else:
                entry["age_bucket"] = "90"
        return entries

    def add_receivable(self, client: str, amount: float, due_date: str, notes: str = "") -> Dict[str, Any]:
        data = self._load_data()
        entry_id = str(uuid.uuid4())
        issue_date = datetime.now().strftime("%Y-%m-%d")

        new_entry = {
            "id": entry_id,
            "client_vendor": client,
            "amount": amount,
            "due_date": due_date,
            "issue_date": issue_date,
            "status": "open",
            "notes": notes,
            "entry_type": "receivable"
        }

        data["receivables"].append(new_entry)
        self._save_data(data)

        # Return the entry with calculated aging
        result = self._calculate_aging([new_entry])[0]
        return result

    def add_payable(self, vendor: str, amount: float, due_date: str, notes: str = "") -> Dict[str, Any]:
        data = self._load_data()
        entry_id = str(uuid.uuid4())
        issue_date = datetime.now().strftime("%Y-%m-%d")

        new_entry = {
            "id": entry_id,
            "client_vendor": vendor,
            "amount": amount,
            "due_date": due_date,
            "issue_date": issue_date,
            "status": "open",
            "notes": notes,
            "entry_type": "payable"
        }

        data["payables"].append(new_entry)
        self._save_data(data)

        # Return the entry with calculated aging
        result = self._calculate_aging([new_entry])[0]
        return result

    def mark_paid(self, entry_id: str, entry_type: str, paid_date: Optional[str] = None) -> Dict[str, Any]:
        if paid_date is None:
            paid_date = datetime.now().strftime("%Y-%m-%d")

        data = self._load_data()
        collection = "receivables" if entry_type == "receivable" else "payables"

        for entry in data[collection]:
            if entry["id"] == entry_id:
                entry["status"] = "paid"
                # Here we would normally auto-post to ledger, but that's handled elsewhere
                self._save_data(data)
                result = self._calculate_aging([entry])[0]
                return result

        raise ValueError(f"Entry {entry_id} not found in {collection}")

    def get_ar_ap(self) -> Dict[str, List[Dict]]:
        data = self._load_data()
        # Calculate aging for both receivables and payables
        data["receivables"] = self._calculate_aging(data["receivables"])
        data["payables"] = self._calculate_aging(data["payables"])
        return data

    def get_aging_report(self) -> Dict[str, List[Dict]]:
        """Get AR/AP data with aging buckets calculated"""
        return self.get_ar_ap()

    def get_overdue_items(self) -> Dict[str, List[Dict]]:
        data = self.get_ar_ap()
        overdue_receivables = [r for r in data["receivables"] if r["days_outstanding"] > 0 and r["status"] == "open"]
        overdue_payables = [p for p in data["payables"] if p["days_outstanding"] > 0 and p["status"] == "open"]
        return {
            "receivables": overdue_receivables,
            "payables": overdue_payables
        }

    def get_upcoming_due(self, days_ahead: int = 7) -> Dict[str, List[Dict]]:
        """Get items due within the next N days"""
        data = self.get_ar_ap()
        upcoming_receivables = [r for r in data["receivables"]
                               if -days_ahead <= r["days_outstanding"] <= 0 and r["status"] == "open"]
        upcoming_payables = [p for p in data["payables"]
                            if -days_ahead <= p["days_outstanding"] <= 0 and p["status"] == "open"]
        return {
            "receivables": upcoming_receivables,
            "payables": upcoming_payables
        }