"""Budget Engine - Budget vs Actual tracking"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

# Ledger row schema: [Date, Description, Category, Amount, Type, Reference, Notes]
_DATE_IDX = 0
_CATEGORY_IDX = 2
_AMOUNT_IDX = 3
_TYPE_IDX = 4


class BudgetEngine:
    def set_budget(self, category: str, amount: float, period: str, business_key: str) -> dict[str, Any]:
        return {
            "id": str(uuid4()),
            "category": category,
            "amount": float(amount),
            "period": period,
            "business_key": business_key,
            "created_at": datetime.now().isoformat(),
        }

    def compute_actuals(
        self,
        budgets: list[dict[str, Any]],
        ledger_rows: list[list[Any]],
        month: str,
    ) -> list[dict[str, Any]]:
        try:
            target_month = datetime.strptime(month, "%Y-%m")
        except ValueError:
            return []

        # Sum expense amounts per category for the target month only
        actuals_by_cat: dict[str, Decimal] = {}
        for row in ledger_rows:
            if len(row) <= _TYPE_IDX:
                continue
            if str(row[_TYPE_IDX]).strip().lower() != "expense":
                continue  # ignore income rows
            try:
                row_date = datetime.strptime(str(row[_DATE_IDX]), "%Y-%m-%d")
            except ValueError:
                continue
            if row_date.year != target_month.year or row_date.month != target_month.month:
                continue
            cat = str(row[_CATEGORY_IDX]).strip().lower() if row[_CATEGORY_IDX] else "uncategorized"
            amount = _parse_amount(row[_AMOUNT_IDX])
            actuals_by_cat[cat] = actuals_by_cat.get(cat, Decimal("0")) + amount

        results: list[dict[str, Any]] = []
        for budget in budgets:
            if budget.get("period") != "monthly":
                continue
            cat = str(budget["category"]).strip().lower()
            budget_amount = Decimal(str(budget["amount"]))
            actual_amount = actuals_by_cat.get(cat, Decimal("0"))
            remaining = budget_amount - actual_amount
            pct = float(actual_amount / budget_amount * 100) if budget_amount > 0 else 0.0
            results.append({
                "id": budget.get("id", ""),
                "category": budget["category"],
                "budget": float(budget_amount),
                "actual": float(actual_amount),
                "remaining": float(remaining),
                "pct": round(pct, 1),
            })

        return results

    def get_alerts(self, actuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        alerts = []
        for item in actuals:
            if item["pct"] >= 80:
                alert = item.copy()
                alert["level"] = "warning" if item["pct"] < 100 else "danger"
                alerts.append(alert)
        return alerts


def _parse_amount(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")
