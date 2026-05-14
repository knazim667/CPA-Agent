"""Orchestrates user commands: routing, AI reasoning, and side effects."""
from __future__ import annotations

import time
from typing import Any

from core.ai_engine import enrich_with_category, self_reflect
from core.command_detectors import (
    detect_business_switch, detect_business_creation, detect_business_rename,
    detect_recurring_command, detect_budget_command, detect_reconcile_command,
    detect_ar_ap_command, detect_tax_command, detect_delete_command,
    detect_split_command, extract_learning_urls, is_learning_request,
    is_recalculation_request,
)
from core.command_dispatch import (
    handle_split_command, handle_budget_command, handle_recurring_command,
    handle_ar_ap_command, handle_tax_command, handle_profile_command,
)
from core.ledger_utils import sheet_url
from core.presentation_builder import build_presentation, clean_response_text


def maybe_store_correction_rule(user_input: str, agent: Any) -> None:
    lowered = user_input.lower()
    correction_markers = (
        "no, that's", "no that is", "actually,",
        "correction:", "you should classify", "it should be",
    )
    if not any(marker in lowered for marker in correction_markers):
        return
    agent.memory.record_custom_rule(user_input=user_input, destination_path=agent.custom_rules_path)
    agent.refresh_rules()


def delete_duplicate_ledger_rows(agent: Any) -> dict[str, Any]:
    profile = agent.memory.get_current_business()
    spreadsheet_id = profile.get("google_sheet_id")
    if not spreadsheet_id:
        return {"ok": False, "message": "No Google Sheet configured for this business."}
    duplicates = agent.sheets.find_duplicate_ledger_rows(spreadsheet_id)
    if not duplicates:
        return {"ok": True, "message": "No duplicate transactions found in the ledger. Everything looks clean."}
    sheet_id = agent.sheets.get_sheet_id(spreadsheet_id, "Ledger")
    indices = [d["sheet_row_index"] for d in duplicates]
    agent.sheets.delete_rows(spreadsheet_id, sheet_id, indices)
    lines = [f"  • {d['date']} | {d['description']} | {d['type']} ${d['amount']}" for d in duplicates]
    return {"ok": True, "message": f"Deleted {len(duplicates)} duplicate row(s) from the ledger:\n" + "\n".join(lines)}


def recalculate_accounts(agent: Any) -> dict[str, Any]:
    profile = agent.ensure_business_workspace_assets()
    workbook = agent.sheets.ensure_financial_workbook(
        spreadsheet_id=profile["google_sheet_id"],
        business_name=profile["business_name"],
    )
    from core.status_builder import get_dashboard_snapshot
    dashboard = get_dashboard_snapshot(agent.memory, agent.sheets, agent.LEDGER_HEADERS)
    return {
        "message": (
            f"I rechecked the workbook for {profile['business_name']}. "
            f"Transactions: {dashboard['transaction_count']}. "
            f"Income: ${dashboard['income_total']:.2f}. "
            f"Expenses: ${dashboard['expense_total']:.2f}. "
            f"Sheet: {sheet_url(profile['google_sheet_id'])}"
        ),
        "dashboard": dashboard,
        "workbook": workbook,
    }


def rename_current_business(new_name: str, agent: Any) -> dict[str, Any]:
    profile = agent.memory.update_business_profile(
        agent.memory.current_business_key, {"business_name": new_name.strip()}
    )
    if profile.get("google_sheet_id"):
        try:
            agent.sheets.rename_spreadsheet(
                spreadsheet_id=profile["google_sheet_id"],
                title=f"{profile['business_name']} CPA Ledger",
            )
        except Exception as exc:  # noqa: BLE001
            agent.workspace_boot_error = str(exc)
    if profile.get("google_doc_id"):
        try:
            agent.docs.rename_document(
                document_id=profile["google_doc_id"],
                title=f"{profile['business_name']} CPA Notes",
            )
        except Exception as exc:  # noqa: BLE001
            agent.workspace_boot_error = str(exc)
    return profile


def learn_from_urls(urls: list[str], topic: str, agent: Any) -> dict[str, Any]:
    entries = []
    for url in urls:
        page = agent.knowledge.learn_from_url(url)
        entry = agent.knowledge.make_memory_entry(page, topic=topic)
        agent.memory.record_learned_source(entry)
        entries.append(entry)
    return {"count": len(entries), "entries": entries}


def handle_command(user_input: str, agent: Any) -> str:
    if not user_input:
        return "I heard the wake word, but not the request."
    maybe_store_correction_rule(user_input, agent)
    if is_recalculation_request(user_input):
        result = recalculate_accounts(agent)
        message = clean_response_text(result["message"])
        agent.memory.append_conversation_entry({
            "timestamp": time.time(), "business": agent.memory.current_business_key,
            "user_input": user_input, "outcome": {"message": message, "details": result},
        })
        return message
    rename_target = detect_business_rename(user_input)
    if rename_target:
        profile = rename_current_business(rename_target, agent)
        message = f"Renamed the active business to {profile['business_name']}."
        agent.memory.append_conversation_entry({
            "timestamp": time.time(), "business": agent.memory.current_business_key,
            "user_input": user_input, "outcome": {"message": message},
        })
        return message
    learn_urls = extract_learning_urls(user_input)
    if learn_urls and is_learning_request(user_input):
        result = learn_from_urls(learn_urls, "google_workspace", agent)
        message = (
            f"Learned from {result['count']} source(s). "
            "I'll use this knowledge for future Google Sheets and Docs work."
        )
        agent.memory.append_conversation_entry({
            "timestamp": time.time(), "business": agent.memory.current_business_key,
            "user_input": user_input, "outcome": {"message": message, "details": result},
        })
        return message
    create_target = detect_business_creation(user_input)
    if create_target:
        business_key, profile, created = agent.memory.create_business(create_target)
        txn_url = None
        agent.workspace_boot_error = None
        try:
            profile = agent.ensure_business_workspace_assets()
            txn_url = sheet_url(profile["google_sheet_id"])
        except Exception as exc:  # noqa: BLE001
            agent.workspace_boot_error = str(exc)
        message = (
            f"Created a new business silo for {profile['business_name']} and switched to it."
            if created else f"{profile['business_name']} already existed, so I switched to it."
        )
        if txn_url:
            message = f"{message} Sheet: {txn_url}"
        elif agent.workspace_boot_error:
            message = f"{message} The local folder and config are ready, but Google workspace setup still needs attention."
        agent.memory.append_conversation_entry({
            "timestamp": time.time(), "business": agent.memory.current_business_key,
            "user_input": user_input,
            "outcome": {"message": message, "details": {"business_key": business_key, "created": created}},
        })
        return message
    switch_target = detect_business_switch(user_input)
    if switch_target:
        profile = agent.memory.switch_business(switch_target)
        profile = agent.ensure_business_workspace_assets()
        message = f"Switched to {profile['business_name']}."
        agent.memory.append_conversation_entry({
            "timestamp": time.time(), "business": agent.memory.current_business_key,
            "user_input": user_input, "outcome": {"message": message},
        })
        return message
    plan = agent.run_reasoning(enrich_with_category(user_input, agent.categorization))
    draft_result = agent.execute_action(plan, user_input)
    reflection = self_reflect(
        user_input, draft_result,
        reflection_client=agent.reflection_client,
        memory=agent.memory,
        custom_rules=agent.custom_rules,
    )
    if reflection.get("approved"):
        final_message = reflection.get("corrected_message") or draft_result["message"]
    else:
        final_message = reflection.get(
            "corrected_message",
            "I found a possible issue during verification and paused the action.",
        )
        draft_result["status"] = "needs_review"
        draft_result["reflection_concerns"] = reflection.get("concerns", [])
    agent.memory.record_skill_outcome(
        action_name=plan.get("action", "respond"),
        success=bool(reflection.get("approved")),
        details={"user_input": user_input, "plan": plan, "draft_result": draft_result, "reflection": reflection},
    )
    agent.memory.append_conversation_entry({
        "timestamp": time.time(), "business": agent.memory.current_business_key,
        "user_input": user_input, "outcome": {**draft_result, "message": final_message},
    })
    return clean_response_text(final_message)


def handle_command_with_metadata(user_input: str, agent: Any) -> dict[str, Any]:
    delete_cmd = detect_delete_command(user_input)
    if delete_cmd and delete_cmd.get("action") == "delete_duplicates":
        result = delete_duplicate_ledger_rows(agent)
        agent.memory.append_conversation_entry({"user_input": user_input, "outcome": {"message": result["message"]}})
        return {"message": result["message"], "status": agent.get_status(), "presentation": None}

    split_cmd = detect_split_command(user_input)
    if split_cmd:
        return handle_split_command(split_cmd, user_input, agent)

    budget_cmd = detect_budget_command(user_input)
    if budget_cmd:
        return handle_budget_command(budget_cmd, agent)

    recurring_cmd = detect_recurring_command(user_input)
    if recurring_cmd:
        return handle_recurring_command(recurring_cmd, user_input, agent)

    reconcile_cmd = detect_reconcile_command(user_input)
    if reconcile_cmd:
        return {"message": "Please use the Reconcile tab in the UI to upload and match bank statements.",
                "status": agent.get_status(), "presentation": None}

    ar_ap_cmd = detect_ar_ap_command(user_input)
    if ar_ap_cmd:
        return handle_ar_ap_command(ar_ap_cmd, user_input, agent)

    tax_cmd = detect_tax_command(user_input)
    if tax_cmd:
        return handle_tax_command(tax_cmd, agent)

    profile_response = handle_profile_command(user_input.lower(), user_input, agent)
    if profile_response is not None:
        return profile_response

    message = handle_command(user_input, agent)
    status = agent.get_status()
    conversation = status.get("conversation", [])
    latest_outcome = conversation[-1].get("outcome", {}) if conversation else {}
    presentation = build_presentation(latest_outcome, status, message, agent.LEDGER_HEADERS)
    return {"message": message, "status": status, "presentation": presentation}
