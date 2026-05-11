"""Row normalization, ledger queries, and sheet write helpers. No AI calls, no business logic."""
from __future__ import annotations

import re
from typing import Any

LEDGER_HEADERS = ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]


def normalize_row(row: list[Any]) -> list[Any]:
    normalized = list(row[:7])
    while len(normalized) < 7:
        normalized.append("")
    if len(normalized) >= 5 and not normalized[4]:
        normalized[4] = "Expense"
    if len(normalized) >= 3 and not normalized[2]:
        normalized[2] = "Uncategorized"
    return normalized


def normalize_bulk_values(values: Any) -> list[list[Any]]:
    if not values or not isinstance(values, list):
        return []
    normalized = []
    for row in values:
        if isinstance(row, list):
            normalized_row = normalize_row(row)
            if normalized_row:
                normalized.append(normalized_row)
    return normalized


def safe_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def sheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def summarize_ledger_rows(
    rows: list[list[Any]],
    ledger_headers: list[str] | None = None,
) -> dict[str, Any]:
    headers = ledger_headers or LEDGER_HEADERS
    if not rows:
        return {"income_total": 0.0, "expense_total": 0.0, "transaction_count": 0, "recent_transactions": []}
    data_rows = rows[1:] if rows[0][: len(headers)] == headers else rows
    income_total = 0.0
    expense_total = 0.0
    parsed_rows: list[dict[str, Any]] = []
    for row in data_rows:
        if len(row) < 5:
            continue
        amount = safe_float(row[3] if len(row) > 3 else 0)
        entry_type = str(row[4]).strip().lower()
        record = {
            "date": str(row[0]) if len(row) > 0 else "",
            "description": str(row[1]) if len(row) > 1 else "",
            "category": str(row[2]) if len(row) > 2 else "",
            "amount": round(amount, 2),
            "type": str(row[4]) if len(row) > 4 else "",
            "reference": str(row[5]) if len(row) > 5 else "",
            "notes": str(row[6]) if len(row) > 6 else "",
        }
        parsed_rows.append(record)
        if entry_type == "income":
            income_total += amount
        else:
            expense_total += amount
    return {
        "income_total": income_total,
        "expense_total": expense_total,
        "transaction_count": len(parsed_rows),
        "recent_transactions": list(reversed(parsed_rows[-5:])),
    }


def build_row_values_from_plan(parameters: dict[str, Any]) -> list[Any]:
    row_values = parameters.get("row_values")
    if row_values:
        return normalize_row(row_values)
    if parameters.get("date") and parameters.get("description") and parameters.get("amount") is not None:
        category = parameters.get("category") or parameters.get("account") or "Uncategorized"
        transaction_type = parameters.get("type") or parameters.get("entry_type") or "Expense"
        return normalize_row([
            parameters.get("date", ""),
            parameters.get("description", ""),
            category,
            parameters.get("amount", ""),
            transaction_type,
            parameters.get("reference", ""),
            parameters.get("notes", ""),
        ])
    return []


def infer_dates_from_text(text: str) -> dict[str, str]:
    mappings: dict[str, str] = {}
    all_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
    if not all_dates:
        return mappings
    mappings["default"] = all_dates[-1]
    for match in re.finditer(
        r"(?P<label>[A-Za-z0-9 /]+?)\s+(?:is on|dated)\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})",
        text,
        re.IGNORECASE,
    ):
        mappings[match.group("label").strip().lower()] = match.group("date")
    return mappings


def infer_bulk_values_from_user_input(
    user_input: str,
    parameters: dict[str, Any],
) -> list[list[Any]]:
    lines = [line.strip(" -\t") for line in user_input.splitlines() if line.strip()]
    extracted_items: list[tuple[str, float]] = []
    for line in lines:
        match = re.match(r"(.+?)\s*[:\-]\s*\$?([0-9]+(?:\.[0-9]{1,2})?)$", line)
        if match:
            extracted_items.append((match.group(1).strip(), float(match.group(2))))
    if not extracted_items:
        return []
    default_category = parameters.get("category") or parameters.get("account") or "Start-up Costs"
    entry_type = parameters.get("type") or parameters.get("entry_type") or "Expense"
    date_map = infer_dates_from_text(user_input)
    fallback_date = parameters.get("date") or date_map.get("default") or ""
    text_lines = user_input.splitlines()
    rows = []
    for description, amount in extracted_items:
        matched_date = fallback_date
        desc_line_idx = next(
            (i for i, line in enumerate(text_lines) if description.lower() in line.lower()), -1
        )
        if desc_line_idx >= 0 and len(date_map) > 1:
            preceding = "\n".join(text_lines[: desc_line_idx + 1])
            preceding_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", preceding)
            if preceding_dates:
                matched_date = preceding_dates[-1]
        for label, label_date in date_map.items():
            if label != "default" and label in description.lower():
                matched_date = label_date
                break
        rows.append(normalize_row([
            matched_date, description, default_category, amount, entry_type, "",
            parameters.get("notes", ""),
        ]))
    return rows


def next_ledger_row_number(sheets: Any, spreadsheet_id: str, worksheet_name: str) -> int:
    rows = sheets.read_range(spreadsheet_id=spreadsheet_id, range_name=f"{worksheet_name}!A:A")
    return max(2, len(rows) + 1)


def verify_sheet_write(
    sheets: Any,
    spreadsheet_id: str,
    range_name: str,
) -> dict[str, Any]:
    try:
        values = sheets.read_range(spreadsheet_id=spreadsheet_id, range_name=range_name)
        verified = any(any(str(cell).strip() for cell in row) for row in values)
        return {"verified": verified, "range_name": range_name, "values": values}
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "range_name": range_name, "error": str(exc)}
