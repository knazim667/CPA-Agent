"""Financial Statements Engine - Balance Sheet & Cash Flow"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


# Ledger row schema: [Date, Description, Category, Amount, Type, Reference, Notes]
_DATE_IDX = 0
_CATEGORY_IDX = 2
_AMOUNT_IDX = 3
_TYPE_IDX = 4

# Category → cash flow activity mapping
_INVESTING_CATS = {"equipment", "vehicles", "property", "investments"}
_FINANCING_CATS = {"loan", "loan payment", "interest"}


class FinancialStatements:
    def compute_balance_sheet(
        self,
        ledger_rows: list[list[Any]],
        ar_ap_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ytd_income = Decimal("0")
        ytd_expenses = Decimal("0")

        for row in ledger_rows:
            if len(row) <= _TYPE_IDX:
                continue
            entry_type = str(row[_TYPE_IDX]).strip().lower()
            amount = _parse_amount(row[_AMOUNT_IDX])
            if entry_type == "income":
                ytd_income += amount
            elif entry_type == "expense":
                ytd_expenses += amount

        net_income = ytd_income - ytd_expenses

        ar_total = Decimal("0")
        ap_total = Decimal("0")
        if ar_ap_data:
            for ar in ar_ap_data.get("receivables", []):
                if ar.get("status") == "open":
                    ar_total += Decimal(str(ar.get("amount", 0)))
            for ap in ar_ap_data.get("payables", []):
                if ap.get("status") == "open":
                    ap_total += Decimal(str(ap.get("amount", 0)))

        # Simplified model: Cash ≈ net YTD income (no bank balance tracked)
        cash = net_income
        total_assets = cash + ar_total
        total_liabilities = ap_total
        total_equity = net_income

        balanced = abs(total_assets - total_liabilities - total_equity) < Decimal("0.01")

        return {
            "assets": {
                "cash": float(cash),
                "accounts_receivable": float(ar_total),
                "total": float(total_assets),
            },
            "liabilities": {
                "accounts_payable": float(ap_total),
                "total": float(total_liabilities),
            },
            "equity": {
                "retained_earnings": float(total_equity),
                "total": float(total_equity),
            },
            "balanced": balanced,
            "approximate": not (ar_total > 0 or ap_total > 0),
        }

    def compute_cash_flow(
        self,
        ledger_rows: list[list[Any]],
        period_start: str,
        period_end: str,
    ) -> dict[str, Any]:
        start = datetime.fromisoformat(period_start)
        end = datetime.fromisoformat(period_end)

        operating = Decimal("0")
        investing = Decimal("0")
        financing = Decimal("0")

        for row in ledger_rows:
            if len(row) <= _TYPE_IDX:
                continue
            try:
                row_date = datetime.strptime(str(row[_DATE_IDX]), "%Y-%m-%d")
            except ValueError:
                continue
            if not (start <= row_date <= end):
                continue

            amount = _parse_amount(row[_AMOUNT_IDX])
            entry_type = str(row[_TYPE_IDX]).strip().lower()
            category = str(row[_CATEGORY_IDX]).strip().lower() if row[_CATEGORY_IDX] else ""

            # Determine sign: income = inflow (+), expense = outflow (-)
            signed = amount if entry_type == "income" else -amount

            if category in _INVESTING_CATS:
                investing += signed
            elif category in _FINANCING_CATS:
                financing += signed
            else:
                operating += signed

        net_change = operating + investing + financing
        return {
            "operating": float(operating),
            "investing": float(investing),
            "financing": float(financing),
            "net_change": float(net_change),
        }


def _parse_amount(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")
