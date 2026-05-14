"""Builds rich presentation payloads for the UI."""
from __future__ import annotations

import re
from typing import Any

from core.ledger_utils import normalize_row, safe_float


def clean_response_text(text: str) -> str:
    cleaned = text.replace("**", "").replace("###", "").replace("---", "\n")
    cleaned = cleaned.replace("•", "-")
    if cleaned.count("|") > 6:
        cleaned = re.sub(r"\|\s*[-:]+\s*", "|", cleaned)
        cleaned = cleaned.replace("|", "\n")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" +\n", "\n", cleaned)
    cleaned = re.sub(r"\n +", "\n", cleaned)
    return cleaned.strip()


def build_presentation(
    outcome: dict[str, Any],
    status: dict[str, Any],
    message: str,
    ledger_headers: list,
) -> dict[str, Any] | None:
    details = outcome.get("details", {}) if isinstance(outcome, dict) else {}
    dashboard = status.get("dashboard", {})
    active_business = status.get("active_business", {})
    if isinstance(details, dict) and "sheet_url" in details:
        verification = details.get("verification", {})
        rows = verification.get("values", []) if isinstance(verification, dict) else []
        normalized_rows = [normalize_row(row) for row in rows if isinstance(row, list)]
        total = sum(safe_float(row[3]) for row in normalized_rows)
        return {
            "kind": "transaction_result",
            "title": f"{active_business.get('business_name', 'Business')} Ledger Update",
            "sheet_url": details.get("sheet_url"),
            "summary_items": [
                {"label": "Rows Written", "value": str(len(normalized_rows))},
                {"label": "Verified", "value": "Yes" if verification.get("verified") else "No"},
                {"label": "Total Amount", "value": f"${total:.2f}"},
            ],
            "table": {
                "columns": ledger_headers,
                "rows": normalized_rows,
            },
        }
    if isinstance(details, dict) and "dashboard" in details:
        dashboard_payload = details["dashboard"]
        return {
            "kind": "account_review",
            "title": f"{active_business.get('business_name', 'Business')} Account Review",
            "summary_items": [
                {"label": "Transactions", "value": str(dashboard_payload.get("transaction_count", 0))},
                {"label": "Income", "value": f"${dashboard_payload.get('income_total', 0):.2f}"},
                {"label": "Expenses", "value": f"${dashboard_payload.get('expense_total', 0):.2f}"},
                {"label": "Flagged", "value": str(dashboard_payload.get("flagged_actions", 0))},
            ],
        }
    if isinstance(details, dict) and details.get("count"):
        entries = details.get("entries", [])
        return {
            "kind": "learning_result",
            "title": "Knowledge Updated",
            "summary_items": [
                {"label": "Sources Learned", "value": str(details.get("count", 0))},
                {"label": "Stored Sources", "value": str(status.get("learned_source_count", 0))},
            ],
            "sources": [
                {"title": entry.get("title", "Untitled"), "url": entry.get("url", "")}
                for entry in entries
            ],
        }
    if dashboard and ("sheet:" in message.lower() or "rechecked the workbook" in message.lower()):
        return {
            "kind": "account_review",
            "title": f"{active_business.get('business_name', 'Business')} Account Review",
            "summary_items": [
                {"label": "Transactions", "value": str(dashboard.get("transaction_count", 0))},
                {"label": "Income", "value": f"${dashboard.get('income_total', 0):.2f}"},
                {"label": "Expenses", "value": f"${dashboard.get('expense_total', 0):.2f}"},
                {"label": "Flagged", "value": str(dashboard.get("flagged_actions", 0))},
            ],
        }
    return None
