"""Dispatches AI action plans to the correct skill."""
from __future__ import annotations

import time
from typing import Any, Callable

from core.ledger_utils import (
    normalize_bulk_values,
    infer_bulk_values_from_user_input,
    build_row_values_from_plan,
    next_ledger_row_number,
    verify_sheet_write,
    safe_float,
    sheet_url,
)
from core.command_detectors import detect_business_switch, detect_business_creation

ACTION_SWITCH_BUSINESS = "switch_business"
ACTION_CREATE_BUSINESS = "create_business"
ACTION_RECORD_TRANSACTION = "record_transaction"
ACTION_READ_SHEET = "read_sheet"
ACTION_CREATE_BUSINESS_DOC = "create_business_doc"
ACTION_APPEND_DOC_NOTE = "append_doc_note"
ACTION_CALCULATE_PAYROLL = "calculate_payroll"
ACTION_RESEARCH_TAX = "research_tax"
ACTION_RESPOND = "respond"


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


def execute_action(
    plan: dict[str, Any],
    user_input: str,
    *,
    sheets: Any,
    docs: Any,
    memory: Any,
    ensure_workspace: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    action = plan.get("action", ACTION_RESPOND)
    parameters = plan.get("parameters", {})

    if action == ACTION_SWITCH_BUSINESS:
        business_name = parameters.get("business_name") or detect_business_switch(user_input)
        if not business_name:
            raise ValueError("Business switch requested without a business name.")
        new_profile = memory.switch_business(business_name)
        return {
            "status": "success",
            "message": f"Switched to {new_profile['business_name']}.",
            "details": new_profile,
        }

    if action == ACTION_CREATE_BUSINESS:
        business_name = parameters.get("business_name") or detect_business_creation(user_input)
        if not business_name:
            raise ValueError("Business creation requested without a business name.")
        state = parameters.get("state", "")
        currency = parameters.get("default_books_currency", "USD")
        business_key, profile, created = memory.create_business(
            business_name, state=state, default_currency=currency
        )
        workspace_url = None
        workspace_boot_error = None
        try:
            profile = ensure_workspace()
            workspace_url = sheet_url(profile["google_sheet_id"])
        except Exception as exc:  # noqa: BLE001
            workspace_boot_error = str(exc)
        status = "success" if created else "noop"
        prefix = "Created" if created else "Switched to existing"
        message = f"{prefix} business {profile['business_name']}."
        if workspace_url:
            message = f"{message} Sheet: {workspace_url}"
        elif workspace_boot_error:
            message = f"{message} Local silo is ready, but Google workspace setup still needs attention."
        return {
            "status": status,
            "message": message,
            "details": {
                "business_key": business_key,
                "created": created,
                "profile": profile,
                "sheet_url": workspace_url,
                "workspace_boot_error": workspace_boot_error,
            },
        }

    if action == ACTION_RECORD_TRANSACTION:
        profile = ensure_workspace()
        values = normalize_bulk_values(parameters.get("values"))
        if not values:
            inferred = infer_bulk_values_from_user_input(user_input, parameters)
            if inferred:
                values = inferred
        row_values = build_row_values_from_plan(parameters)
        worksheet_name = parameters.get("worksheet_name", "Ledger")
        txn_url = sheet_url(profile["google_sheet_id"])
        if values:
            start_row = next_ledger_row_number(sheets, profile["google_sheet_id"], worksheet_name)
            end_row = start_row + len(values) - 1
            range_name = parameters.get("range") or f"{worksheet_name}!A{start_row}:G{end_row}"
            result = sheets.update_range(
                spreadsheet_id=profile["google_sheet_id"],
                range_name=range_name,
                values=values,
            )
            verification = verify_sheet_write(sheets, profile["google_sheet_id"], range_name)
            _record_audit(mode="bulk_update", requested_payload=values, result=result, verification=verification, memory=memory)
            if not verification["verified"]:
                return {
                    "status": "needs_review",
                    "message": "I could not verify that the transaction rows were written to the sheet.",
                    "details": {"result": result, "verification": verification, "sheet_url": txn_url},
                }
            return {
                "status": "success",
                "message": f"Transactions recorded. Sheet: {txn_url}",
                "details": {"result": result, "verification": verification, "sheet_url": txn_url},
            }
        if not row_values:
            return {
                "status": "needs_review",
                "message": "I could not record that transaction because the ledger row was incomplete.",
                "details": {"plan_parameters": parameters, "sheet_url": txn_url},
            }
        result = sheets.append_ledger_row(
            spreadsheet_id=profile["google_sheet_id"],
            worksheet_name=worksheet_name,
            row_values=row_values,
        )
        updated_range = result.get("updates", {}).get("updatedRange")
        verification = verify_sheet_write(
            sheets, profile["google_sheet_id"], updated_range or f"{worksheet_name}!A:Z"
        )
        _record_audit(mode="append", requested_payload=row_values, result=result, verification=verification, memory=memory)
        if not verification["verified"]:
            return {
                "status": "needs_review",
                "message": "I could not verify that the transaction was written to the sheet.",
                "details": {"result": result, "verification": verification, "sheet_url": txn_url},
            }
        return {
            "status": "success",
            "message": f"Transaction recorded. Sheet: {txn_url}",
            "details": {"result": result, "verification": verification, "sheet_url": txn_url},
        }

    if action == ACTION_READ_SHEET:
        profile = ensure_workspace()
        range_name = parameters.get("range_name", "Ledger!A1:Z20")
        if "2000" in range_name:
            range_name = range_name.replace("2000", "200")
        values = sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"],
            range_name=range_name,
        )
        return {"status": "success", "message": "Sheet data retrieved.", "details": values}

    if action == ACTION_CREATE_BUSINESS_DOC:
        profile = ensure_workspace()
        return {
            "status": "success",
            "message": "Business document is ready.",
            "details": {"document_id": profile["google_doc_id"]},
        }

    if action == ACTION_APPEND_DOC_NOTE:
        profile = ensure_workspace()
        result = docs.append_text(
            document_id=profile["google_doc_id"],
            text=parameters.get("text", ""),
        )
        return {"status": "success", "message": "Document note saved.", "details": result}

    if action == ACTION_CALCULATE_PAYROLL:
        from skills.payroll_engine import calculate_simple_payroll
        gross_pay = safe_float(parameters.get("gross_pay", 0))
        federal_rate = float(parameters.get("federal_rate", 0.12))
        if gross_pay <= 0:
            return {
                "status": "needs_review",
                "message": "Gross pay must be a positive number.",
                "details": {"parameters": parameters},
            }
        calc = calculate_simple_payroll(gross_pay=gross_pay, federal_rate=federal_rate)
        return {
            "status": "success",
            "message": (
                f"Payroll: Gross ${calc.gross_pay:.2f} | Federal ${calc.federal_withholding:.2f} | "
                f"SS ${calc.social_security:.2f} | Medicare ${calc.medicare:.2f} | Net ${calc.net_pay:.2f}."
            ),
            "details": {
                "gross_pay": calc.gross_pay,
                "federal_withholding": calc.federal_withholding,
                "social_security": calc.social_security,
                "medicare": calc.medicare,
                "net_pay": calc.net_pay,
            },
        }

    if action == ACTION_RESEARCH_TAX:
        from skills.tax_researcher import fetch_tax_update
        url = parameters.get("url", "").strip()
        if not url:
            return {"status": "needs_review", "message": "A URL is required for tax research.", "details": {}}
        result = fetch_tax_update(url)
        memory.record_learned_source({"url": result.url, "title": result.title, "summary": result.summary, "topic": "tax"})
        return {
            "status": "success",
            "message": f"Tax research complete. Stored: {result.title}",
            "details": {"url": result.url, "title": result.title, "summary": result.summary},
        }

    return {
        "status": "success",
        "message": plan.get("response", "No tool call was needed."),
        "details": {"action": action, "parameters": parameters},
    }
