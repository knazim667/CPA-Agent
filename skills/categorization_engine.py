from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from skills.chart_of_accounts import classify_transaction as _coa_classify


class CategorizationEngine:
    def __init__(self, rules_data: dict[str, Any] | None = None) -> None:
        self._rules: list[dict[str, Any]] = list((rules_data or {}).get("rules", []))

    def get_rules_data(self) -> dict[str, Any]:
        return {"rules": list(self._rules)}

    def suggest_category(self, description: str) -> dict[str, Any] | None:
        """Return the best category match using learned rules first, then COA fallback."""
        desc_lower = description.lower()
        best: dict[str, Any] | None = None
        for rule in self._rules:
            if rule["pattern"] in desc_lower:
                if best is None or rule.get("confidence", 0) > best.get("confidence", 0):
                    best = rule
        if best is not None:
            return {
                "category": best["category"],
                "confidence": best.get("confidence", 0.8),
                "rule_id": best["id"],
            }
        # COA fallback: deterministic classification based on account/keyword rules
        coa_match = _coa_classify(description)
        if coa_match is not None:
            return {
                "category": coa_match["account_name"],
                "confidence": coa_match["confidence"],
                "ledger_type": coa_match["ledger_type"],
                "note": coa_match["note"],
            }
        return None

    def save_rule(self, description: str, category: str) -> dict[str, Any]:
        pattern = description.strip().lower()
        for rule in self._rules:
            if rule["pattern"] == pattern:
                rule["category"] = category
                rule["confidence"] = min(rule.get("confidence", 0.8) + 0.05, 1.0)
                rule["use_count"] = rule.get("use_count", 0) + 1
                return rule
        new_rule: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "pattern": pattern,
            "match_type": "contains",
            "category": category,
            "confidence": 0.8,
            "use_count": 1,
        }
        self._rules.append(new_rule)
        return new_rule

    def backfill_rules_from_ledger(self, rows: list[list[Any]]) -> int:
        pairs: Counter = Counter()
        for row in rows:
            if len(row) < 3:
                continue
            vendor = str(row[1]).strip().lower()
            category = str(row[2]).strip()
            if vendor and category:
                pairs[(vendor, category)] += 1
        created = 0
        for (vendor, category), count in pairs.items():
            if count >= 2:
                existing = next((r for r in self._rules if r["pattern"] == vendor), None)
                # If a vendor maps to multiple categories, the first pair (by Counter iteration)
                # wins; subsequent conflicting categories are skipped to avoid overwriting.
                if not existing:
                    self._rules.append({
                        "id": str(uuid.uuid4()),
                        "pattern": vendor,
                        "match_type": "contains",
                        "category": category,
                        "confidence": 0.85,
                        "use_count": count,
                    })
                    created += 1
        return created

    def split_transaction(
        self,
        total_amount: float,
        splits: list[dict],
        *,
        date: str = "",
        parent_description: str = "",
        entry_type: str = "Expense",
    ) -> list[list[Any]]:
        # parent_description is accepted for API consistency but each split provides its own description
        _ = parent_description

        if not splits:
            raise ValueError("split_transaction requires at least one split.")
        for i, s in enumerate(splits):
            for key in ("amount", "category", "description"):
                if key not in s:
                    raise ValueError(
                        f"Split {i} is missing required key '{key}'."
                    )
            # Critical #2: Validate numeric type before any arithmetic
            if not isinstance(s["amount"], (int, float)):
                raise ValueError(
                    f"Split {i} 'amount' must be a number, got {type(s['amount']).__name__}."
                )

        # Critical #1: Round amounts before validation to ensure balanced ledger
        rounded_amounts = [round(s["amount"], 2) for s in splits]
        total_split = sum(rounded_amounts)
        if abs(total_split - round(total_amount, 2)) > 0.01:
            raise ValueError(
                f"Split amounts (${total_split:.2f}) do not match total "
                f"(${round(total_amount, 2):.2f})."
            )

        n = len(splits)
        return [
            [
                date,
                splits[i]["description"],
                splits[i]["category"],
                rounded_amounts[i],
                entry_type,
                "",
                f"split {i + 1}/{n}",
            ]
            for i in range(n)
        ]
