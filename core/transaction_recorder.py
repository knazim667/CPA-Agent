"""Writes transactions to the Google Sheet ledger after reflection approval."""
from __future__ import annotations

import json
import time
from typing import Any

from core.ai_engine import parse_json_response, self_reflect
from core.ledger_utils import normalize_row, safe_float, sheet_url, next_ledger_row_number, verify_sheet_write


def _record_audit(
    *,
    mode: str,
    requested_payload: Any,
    result: dict[str, Any],
    verification: dict[str, Any],
    memory: Any,
) -> None:
    memory.record_transaction_audit({
        "timestamp": time.time(),
        "business": memory.current_business_key,
        "mode": mode,
        "requested_payload": requested_payload,
        "result": result,
        "verification": verification,
    })


def record_structured_transaction(
    *,
    date: str,
    description: str,
    category: str,
    amount: float,
    entry_type: str,
    reference: str = "",
    notes: str = "",
    profile: dict[str, Any],
    sheets: Any,
    memory: Any,
    reflection_client: Any,
    custom_rules: dict,
) -> dict[str, Any]:
    sid = profile["google_sheet_id"]
    txn_sheet_url = sheet_url(sid)
    normalized_type = entry_type.strip().title()
    amount_value = round(float(amount), 2)
    row_values = [
        date.strip(), description.strip(), category.strip(),
        amount_value, normalized_type, reference.strip(), notes.strip(),
    ]
    duplicate = sheets.find_duplicate_row(
        spreadsheet_id=sid,
        date=date.strip(),
        amount=str(amount_value),
        entry_type=normalized_type,
    )
    if duplicate and "confirm duplicate" not in notes.lower():
        return {
            "ok": False,
            "message": (
                f"Duplicate detected: a {duplicate['type']} of {duplicate['amount']} "
                f"on {duplicate['date']} ({duplicate['description']}) already exists. "
                "If this is intentional, add 'confirm duplicate' to the Notes field."
            ),
        }
    draft_result = {
        "status": "success",
        "message": f"Prepared a {normalized_type.lower()} transaction for {description.strip()} for ${amount_value:.2f}.",
        "details": {"business": profile["business_name"], "row_values": row_values},
    }
    user_input_str = (
        f"Record {normalized_type.lower()} transaction: {description.strip()} "
        f"({category.strip()}) for ${amount_value:.2f} on {date.strip()}."
    )
    reflection = self_reflect(
        user_input_str,
        draft_result,
        reflection_client=reflection_client,
        memory=memory,
        custom_rules=custom_rules,
    )
    if not reflection.get("approved"):
        return {
            "ok": False,
            "message": reflection.get(
                "corrected_message",
                "I found a possible issue during verification and paused the transaction.",
            ),
            "reflection": reflection,
        }
    result = sheets.append_ledger_row(
        spreadsheet_id=sid, worksheet_name="Ledger", row_values=row_values,
    )
    updated_range = result.get("updates", {}).get("updatedRange")
    verification = verify_sheet_write(sheets, sid, updated_range or "Ledger!A:Z")
    _record_audit(mode="structured_append", requested_payload=row_values, result=result, verification=verification, memory=memory)
    if not verification["verified"]:
        return {
            "ok": False,
            "message": "I could not verify that the structured transaction was written to the sheet.",
            "details": {"result": result, "verification": verification, "sheet_url": txn_sheet_url},
        }
    outcome = {
        "status": "success",
        "message": (
            reflection.get("corrected_message")
            or f"Recorded {normalized_type.lower()} transaction for {description.strip()}."
        ) + f" Sheet: {txn_sheet_url}",
        "details": {"result": result, "verification": verification, "sheet_url": txn_sheet_url},
    }
    recorded_input = (
        f"Structured transaction: {normalized_type.lower()} {description.strip()} "
        f"for ${amount_value:.2f} in {category.strip()}."
    )
    memory.record_skill_outcome(
        action_name="record_transaction",
        success=True,
        details={"user_input": recorded_input, "draft_result": draft_result, "reflection": reflection, "row_values": row_values},
    )
    memory.append_conversation_entry({
        "timestamp": time.time(),
        "business": memory.current_business_key,
        "user_input": recorded_input,
        "outcome": outcome,
    })
    return {
        "ok": True,
        "message": outcome["message"],
        "details": {
            "append_result": result,
            "verification": verification,
            "row_values": row_values,
            "sheet_url": txn_sheet_url,
        },
    }


def record_bulk_transactions(
    rows: list[list[Any]],
    *,
    source_name: str = "",
    source_note: str = "",
    profile: dict[str, Any],
    sheets: Any,
    memory: Any,
    reflection_client: Any,
    custom_rules: dict,
) -> dict[str, Any]:
    sid = profile["google_sheet_id"]
    txn_sheet_url = sheet_url(sid)
    normalized_rows = []
    for row in rows:
        normalized = normalize_row(row)
        if source_name and not normalized[5]:
            normalized[5] = source_name
        if source_note and not normalized[6]:
            normalized[6] = source_note
        normalized_rows.append(normalized)
    if not normalized_rows:
        return {"ok": False, "message": "There were no draft transactions to record.", "details": {"sheet_url": txn_sheet_url}}
    draft_result = {
        "status": "success",
        "message": f"Prepared {len(normalized_rows)} transaction rows for approval.",
        "details": {"business": profile["business_name"], "rows": normalized_rows},
    }
    reflection = self_reflect(
        f"Record {len(normalized_rows)} approved document-based transactions.",
        draft_result,
        reflection_client=reflection_client,
        memory=memory,
        custom_rules=custom_rules,
    )
    if not reflection.get("approved"):
        return {
            "ok": False,
            "message": reflection.get(
                "corrected_message",
                "I found a possible issue during verification and paused these transactions.",
            ),
            "reflection": reflection,
        }
    start_row = next_ledger_row_number(sheets, sid, "Ledger")
    end_row = start_row + len(normalized_rows) - 1
    range_name = f"Ledger!A{start_row}:G{end_row}"
    result = sheets.update_range(spreadsheet_id=sid, range_name=range_name, values=normalized_rows)
    verification = verify_sheet_write(sheets, sid, range_name)
    _record_audit(mode="approved_document_bulk_update", requested_payload=normalized_rows, result=result, verification=verification, memory=memory)
    if not verification["verified"]:
        return {
            "ok": False,
            "message": "I could not verify that the approved document transactions were written to the sheet.",
            "details": {"result": result, "verification": verification, "sheet_url": txn_sheet_url},
        }
    return {
        "ok": True,
        "message": f"Approved document transactions recorded. Sheet: {txn_sheet_url}",
        "details": {"result": result, "verification": verification, "sheet_url": txn_sheet_url, "rows": normalized_rows},
    }


def draft_document_transactions(
    *,
    file_name: str,
    document_text: str,
    instruction: str = "",
    model_client: Any,
    memory: Any,
) -> dict[str, Any]:
    prompt = [
        {
            "role": "system",
            "content": (
                "You are CPA-Agent drafting accounting entries from a source document. "
                "Read the extracted document text and return only JSON with keys summary, rows, concerns. "
                "Each row must contain date, description, category, amount, type, reference, notes. "
                "Use multiple rows if the document has multiple purchases. "
                "Be conservative and do not guess missing values."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "active_business": memory.get_current_business(),
                "instruction": instruction,
                "file_name": file_name,
                "document_text": document_text[:12000],
            }, indent=2),
        },
    ]
    response_text = model_client.chat(prompt)
    payload = parse_json_response(response_text)
    if payload is None:
        return {
            "ok": False,
            "message": "I could not convert that document into a clean draft table yet.",
            "details": {"raw_response": response_text},
        }
    raw_rows = payload.get("rows", [])
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        if item.get("amount") in (None, "") or not item.get("description"):
            continue
        rows.append(normalize_row([
            item.get("date", ""),
            item.get("description", ""),
            item.get("category", "Uncategorized"),
            item.get("amount", ""),
            item.get("type", "Expense"),
            item.get("reference", file_name),
            item.get("notes", ""),
        ]))
    if not rows:
        return {
            "ok": False,
            "message": "I read the document, but I could not draft a reliable expense table from it.",
            "details": {"summary": payload.get("summary", ""), "concerns": payload.get("concerns", [])},
        }
    total_amount = sum(safe_float(row[3]) for row in rows)
    return {
        "ok": True,
        "message": f"I prepared a draft with {len(rows)} row(s) totaling ${total_amount:.2f}. Review it and approve when you're ready.",
        "details": {
            "summary": payload.get("summary", ""),
            "concerns": payload.get("concerns", []),
            "rows": rows,
            "total_amount": round(total_amount, 2),
            "file_name": file_name,
        },
    }
