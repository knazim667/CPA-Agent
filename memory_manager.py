from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

PROFILE_DEFAULTS: dict = {
    "legal_structure": "",        # single_member_llc | multi_member_llc | s_corp | partnership | sole_proprietor
    "industry": "",               # e_commerce | import_export | professional_services | retail | construction | healthcare | content_creator | manufacturing | other
    "business_model": "",         # product_based | service_based | mixed
    "fiscal_year_start": "01-01",
    "accounting_basis": "cash",   # cash | accrual
    "inventory_method": "none",   # fifo | lifo | wac | none
    "operating_states": [],
    "address": {"street": "", "city": "", "state": "", "zip": "", "country": "US"},
    "contact": {"phone": "", "email": ""},
    "owners": [],
    "onboarding_complete": False,
}


class MemoryManager:
    def __init__(self, memory_root: Path) -> None:
        self.memory_root = Path(memory_root)
        self.long_term_dir = self.memory_root / "long_term"
        self.knowledge_dir = self.memory_root / "knowledge"
        self.short_term_path = self.memory_root / "short_term.json"
        self.skill_memory_path = self.memory_root / "skill_memory.json"
        self.transaction_audit_path = self.memory_root / "transaction_audit.json"
        self.learned_sources_path = self.knowledge_dir / "learned_sources.json"
        self.state_path = self.memory_root / "active_business.json"
        self._ensure_files()
        self.current_business_key = self._load_active_business_key()

    def _ensure_files(self) -> None:
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.long_term_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        if not self.short_term_path.exists():
            self.short_term_path.write_text(json.dumps({"conversation": []}, indent=2), encoding="utf-8")
        if not self.skill_memory_path.exists():
            self.skill_memory_path.write_text(
                json.dumps({"history": [], "success_patterns": [], "failure_patterns": []}, indent=2),
                encoding="utf-8",
            )
        if not self.transaction_audit_path.exists():
            self.transaction_audit_path.write_text(json.dumps({"entries": []}, indent=2), encoding="utf-8")
        if not self.learned_sources_path.exists():
            self.learned_sources_path.write_text(json.dumps({"entries": []}, indent=2), encoding="utf-8")
        if not self.state_path.exists():
            default_business = self._discover_business_keys()[0]
            self.state_path.write_text(json.dumps({"active_business": default_business}, indent=2), encoding="utf-8")

    def _discover_business_keys(self) -> list[str]:
        keys = [path.name for path in self.long_term_dir.iterdir() if path.is_dir()]
        if not keys:
            raise FileNotFoundError("No business profiles exist under memory/long_term.")
        return sorted(keys)

    def list_business_keys(self) -> list[str]:
        return self._discover_business_keys()

    def _load_active_business_key(self) -> str:
        with self.state_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload["active_business"]

    @staticmethod
    def normalize_business_key(name: str) -> str:
        normalized = "".join(char if char.isalnum() else "_" for char in name.strip().lower())
        normalized = normalized.strip("_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized or "business"

    def _write_active_business_key(self, business_key: str) -> None:
        self.state_path.write_text(json.dumps({"active_business": business_key}, indent=2), encoding="utf-8")
        self.current_business_key = business_key

    def _profile_path(self, business_key: str) -> Path:
        return self.long_term_dir / business_key / "config.json"

    def load_business_profile(self, business_key: str) -> dict[str, Any]:
        profile_path = self._profile_path(business_key)
        if not profile_path.exists():
            raise FileNotFoundError(f"Business profile not found for {business_key}.")
        with profile_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_business_profile(self, business_key: str, profile: dict[str, Any]) -> None:
        profile_path = self._profile_path(business_key)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    def create_business(
        self,
        business_name: str,
        *,
        state: str = "",
        default_currency: str = "USD",
    ) -> tuple[str, dict[str, Any], bool]:
        cleaned_name = business_name.strip()
        if not cleaned_name:
            raise ValueError("Business name is required.")

        existing_keys = self._discover_business_keys()
        existing_by_name = {
            self.load_business_profile(key)["business_name"].strip().lower(): key
            for key in existing_keys
        }
        existing_key = existing_by_name.get(cleaned_name.lower())
        if existing_key:
            profile = self.load_business_profile(existing_key)
            self._write_active_business_key(existing_key)
            self.reset_short_term_context()
            return existing_key, profile, False

        base_key = self.normalize_business_key(cleaned_name)
        business_key = base_key
        suffix = 2
        while business_key in existing_keys:
            business_key = f"{base_key}_{suffix}"
            suffix += 1

        db_name = f"{business_key}.db"
        profile = {
            **copy.deepcopy(PROFILE_DEFAULTS),
            "business_name": cleaned_name,
            "google_sheet_id": "replace-with-sheet-id",
            "google_doc_id": "replace-with-doc-id",
            "local_memory_db": f"memory/long_term/{business_key}/{db_name}",
            "federal_ein": "",
            "state": state.strip().upper(),
            "default_books_currency": default_currency.strip().upper() or "USD",
        }
        profile_path = self._profile_path(business_key)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        local_db_path = profile_path.parent / db_name
        local_db_path.touch(exist_ok=True)
        self.save_business_profile(business_key, profile)
        self._write_active_business_key(business_key)
        self.reset_short_term_context()
        return business_key, profile, True

    def update_business_profile(self, business_key: str, updates: dict[str, Any]) -> dict[str, Any]:
        profile = self.load_business_profile(business_key)
        profile.update(updates)
        self.save_business_profile(business_key, profile)
        return profile

    def switch_business(self, business_name: str) -> dict[str, Any]:
        normalized = business_name.strip().lower().replace(" ", "_").replace("-", "_")
        candidates = {key.lower(): key for key in self._discover_business_keys()}
        if normalized in candidates:
            business_key = candidates[normalized]
        else:
            by_display_name = {
                self.load_business_profile(key)["business_name"].lower(): key
                for key in self._discover_business_keys()
            }
            if business_name.strip().lower() not in by_display_name:
                raise ValueError(f"Unknown business '{business_name}'.")
            business_key = by_display_name[business_name.strip().lower()]

        profile = self.load_business_profile(business_key)
        self._write_active_business_key(business_key)
        self.reset_short_term_context()
        return profile

    def get_current_business(self) -> dict[str, Any]:
        return self.load_business_profile(self.current_business_key)

    def load_short_term_context(self) -> dict[str, Any]:
        with self.short_term_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_skill_memory(self) -> dict[str, Any]:
        with self.skill_memory_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def reset_short_term_context(self) -> None:
        payload = {
            "active_business": self.current_business_key,
            "conversation": [],
            "last_reset": time.time(),
        }
        self.short_term_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def append_conversation_entry(self, entry: dict[str, Any]) -> None:
        payload = self.load_short_term_context()
        payload.setdefault("active_business", self.current_business_key)
        payload.setdefault("conversation", []).append(entry)
        self.short_term_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_skill_outcome(self, action_name: str, success: bool, details: dict[str, Any]) -> None:
        with self.skill_memory_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        record = {
            "timestamp": time.time(),
            "business": self.current_business_key,
            "action_name": action_name,
            "success": success,
            "details": details,
        }
        payload.setdefault("history", []).append(record)

        bucket = "success_patterns" if success else "failure_patterns"
        payload.setdefault(bucket, []).append(
            {
                "action_name": action_name,
                "business": self.current_business_key,
                "timestamp": record["timestamp"],
            }
        )
        self.skill_memory_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_custom_rule(self, user_input: str, destination_path: Path) -> None:
        if destination_path.exists():
            with destination_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            payload = {"rules": []}

        payload.setdefault("rules", []).append(
            {
                "timestamp": time.time(),
                "business": self.current_business_key,
                "rule": user_input.strip(),
            }
        )
        destination_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_transaction_audit(self, entry: dict[str, Any]) -> None:
        with self.transaction_audit_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload.setdefault("entries", []).append(entry)
        self.transaction_audit_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_transaction_audit(self) -> dict[str, Any]:
        with self.transaction_audit_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def record_learned_source(self, entry: dict[str, Any]) -> None:
        with self.learned_sources_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload.setdefault("entries", []).append(entry)
        self.learned_sources_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_learned_sources(self) -> dict[str, Any]:
        with self.learned_sources_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _category_rules_path(self) -> Path:
        return self.long_term_dir / self.current_business_key / "category_rules.json"

    def load_category_rules(self) -> dict[str, Any]:
        path = self._category_rules_path()
        if not path.exists():
            return {"rules": []}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_category_rules(self, data: dict[str, Any]) -> None:
        path = self._category_rules_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _recurring_path(self) -> Path:
        return self.long_term_dir / self.current_business_key / "recurring.json"

    def load_recurring(self) -> dict[str, Any]:
        path = self._recurring_path()
        if not path.exists():
            return {"schedules": []}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_recurring(self, data: dict[str, Any]) -> None:
        path = self._recurring_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _budgets_path(self) -> Path:
        return self.long_term_dir / self.current_business_key / "budgets.json"

    def load_budgets(self) -> dict[str, Any]:
        path = self._budgets_path()
        if not path.exists():
            return {"budgets": []}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_budgets(self, data: dict[str, Any]) -> None:
        path = self._budgets_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _m1_state_path(self) -> Path:
        return self.long_term_dir / self.current_business_key / "m1_state.json"

    def load_m1_state(self) -> dict[str, Any]:
        path = self._m1_state_path()
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_m1_state(self, data: dict[str, Any]) -> None:
        path = self._m1_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _m1_category_map_path(self) -> Path:
        return self.long_term_dir / self.current_business_key / "m1_category_map.json"

    def load_m1_category_map(self) -> dict[str, str]:
        path = self._m1_category_map_path()
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_m1_category_map(self, data: dict[str, str]) -> None:
        path = self._m1_category_map_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def migrate_business_profiles(self) -> None:
        """Add missing onboarding fields to existing config.json files."""
        for key in self.list_business_keys():
            try:
                profile = self.load_business_profile(key)
                changed = False
                for field, default in PROFILE_DEFAULTS.items():
                    if field not in profile:
                        profile[field] = copy.deepcopy(default)
                        changed = True
                if changed:
                    self.save_business_profile(key, profile)
            except (FileNotFoundError, json.JSONDecodeError):
                pass
