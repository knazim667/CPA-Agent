"""Status and dashboard payload builders. No AI calls, no side effects."""
from __future__ import annotations

import os
from typing import Any

from core.ledger_utils import summarize_ledger_rows


def get_dashboard_snapshot(memory: Any, sheets: Any, ledger_headers: list) -> dict[str, Any]:
    current = memory.get_current_business()
    skill_memory = memory.load_skill_memory()
    transaction_audit = memory.load_transaction_audit().get("entries", [])
    conversation = memory.load_short_term_context().get("conversation", [])
    totals: dict[str, Any] = {
        "income_total": 0.0,
        "expense_total": 0.0,
        "transaction_count": 0,
        "recent_transactions": [],
    }
    if current.get("google_sheet_id"):
        try:
            rows = sheets.read_range(
                spreadsheet_id=current["google_sheet_id"],
                range_name="Ledger!A1:G100",
            )
            totals = summarize_ledger_rows(rows, ledger_headers)
        except Exception as exc:  # noqa: BLE001
            totals["ledger_error"] = str(exc)
    success_history = [item for item in skill_memory.get("history", []) if item.get("success")]
    failure_history = [item for item in skill_memory.get("history", []) if not item.get("success")]
    recent_audits = [
        entry for entry in transaction_audit
        if entry.get("business") == memory.current_business_key
    ][-5:]
    return {
        "active_business_name": current["business_name"],
        "transaction_count": totals["transaction_count"],
        "income_total": round(totals["income_total"], 2),
        "expense_total": round(totals["expense_total"], 2),
        "recent_transactions": totals["recent_transactions"],
        "recent_audits": recent_audits,
        "conversation_count": len(conversation),
        "successful_actions": len(success_history),
        "flagged_actions": len(failure_history),
        "ledger_error": totals.get("ledger_error"),
    }


def get_model_status(reasoning_mode: str) -> dict[str, str]:
    provider = os.getenv("MODEL_PROVIDER", "ollama").strip().lower() or "ollama"
    if provider == "ollama":
        reasoning_model = (
            os.getenv("OLLAMA_QUALITY_MODEL")
            if reasoning_mode == "quality" and os.getenv("OLLAMA_QUALITY_MODEL")
            else os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
        )
        reflection_model = (
            os.getenv("OLLAMA_REFLECTION_MODEL")
            or os.getenv("OLLAMA_AUDIT_MODEL")
            or reasoning_model
        )
    elif provider == "openai":
        reasoning_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        reflection_model = reasoning_model
    elif provider == "openrouter":
        reasoning_model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        reflection_model = reasoning_model
    else:
        reasoning_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        reflection_model = reasoning_model
    return {
        "provider": provider,
        "reasoning_mode": reasoning_mode,
        "reasoning_model": reasoning_model,
        "reflection_model": reflection_model,
    }


def build_status(agent: Any) -> dict[str, Any]:
    from datetime import date
    due: list = []
    today_str = date.today().isoformat()
    if today_str != getattr(agent, "_last_schedule_check", None):
        due = agent.recurring.run_due_schedules()
        agent._last_schedule_check = today_str
    if due:
        agent._save_recurring()
        for entry in due:
            try:
                agent.record_structured_transaction(
                    date=entry.get("last_posted_date", ""),
                    description=entry["description"],
                    category=entry["category"],
                    amount=entry["amount"],
                    entry_type=entry["entry_type"],
                    notes="Auto-posted by recurring schedule",
                )
            except Exception as exc:  # noqa: BLE001
                agent.memory.record_skill_outcome(
                    action_name="recurring_auto_post",
                    success=False,
                    details={"error": str(exc), "entry": entry},
                )
    short_term = agent.memory.load_short_term_context()
    current = agent.memory.get_current_business()
    raw_conv = short_term.get("conversation", [])
    conversation = []
    for entry in raw_conv:
        if entry.get("user_input"):
            conversation.append({"role": "user", "content": entry["user_input"]})
        if entry.get("outcome", {}).get("message"):
            conversation.append({"role": "agent", "content": entry["outcome"]["message"]})
    overdue_ar_ap: dict = {"receivables": [], "payables": []}
    upcoming_ar_ap: dict = {"receivables": [], "payables": []}
    try:
        overdue_ar_ap = agent.ar_ap_engine.get_overdue_items()
        upcoming_ar_ap = agent.ar_ap_engine.get_upcoming_due(days_ahead=7)
    except Exception:  # noqa: BLE001
        pass
    return {
        "active_business_key": agent.memory.current_business_key,
        "active_business": current,
        "businesses": agent.list_businesses(),
        "conversation": conversation,
        "workspace_boot_error": agent.workspace_boot_error,
        "input_mode": agent.input_mode,
        "model_config": get_model_status(agent.reasoning_mode),
        "dashboard": get_dashboard_snapshot(agent.memory, agent.sheets, agent.LEDGER_HEADERS),
        "learned_source_count": len(agent.memory.load_learned_sources().get("entries", [])),
        "tax_alerts": agent.tax_engine.get_upcoming_alerts(days_ahead=60),
        "overdue_ar_ap": overdue_ar_ap,
        "upcoming_ar_ap": upcoming_ar_ap,
    }
