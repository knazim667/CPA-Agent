"""Low-level JSON store helpers and constants shared with MemoryManager."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

PROFILE_DEFAULTS: dict = {
    "legal_structure": "",
    "industry": "",
    "business_model": "",
    "fiscal_year_start": "01-01",
    "accounting_basis": "cash",
    "inventory_method": "none",
    "operating_states": [],
    "address": {"street": "", "city": "", "state": "", "zip": "", "country": "US"},
    "contact": {"phone": "", "email": ""},
    "owners": [],
    "onboarding_complete": False,
}


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_skill_outcome(
    skill_memory_path: Path,
    business_key: str,
    action_name: str,
    success: bool,
    details: dict[str, Any],
) -> None:
    with skill_memory_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    record = {
        "timestamp": time.time(),
        "business": business_key,
        "action_name": action_name,
        "success": success,
        "details": details,
    }
    payload.setdefault("history", []).append(record)
    bucket = "success_patterns" if success else "failure_patterns"
    payload.setdefault(bucket, []).append({
        "action_name": action_name,
        "business": business_key,
        "timestamp": record["timestamp"],
    })
    skill_memory_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def record_custom_rule(destination_path: Path, business_key: str, user_input: str) -> None:
    payload = load_json(destination_path, {"rules": []})
    payload.setdefault("rules", []).append({
        "timestamp": time.time(),
        "business": business_key,
        "rule": user_input.strip(),
    })
    destination_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def record_audit_entry(path: Path, entry: dict[str, Any]) -> None:
    payload = load_json(path, {"entries": []})
    payload.setdefault("entries", []).append(entry)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def record_learned_source(path: Path, entry: dict[str, Any]) -> None:
    payload = load_json(path, {"entries": []})
    payload.setdefault("entries", []).append(entry)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def migrate_business_profiles(
    list_keys_fn: Any, load_fn: Any, save_fn: Any
) -> None:
    for key in list_keys_fn():
        try:
            profile = load_fn(key)
            changed = False
            for field, default in PROFILE_DEFAULTS.items():
                if field not in profile:
                    profile[field] = copy.deepcopy(default)
                    changed = True
            if changed:
                save_fn(key, profile)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
