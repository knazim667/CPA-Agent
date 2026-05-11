"""AI message construction, reasoning, and self-reflection helpers."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse


def build_financial_context(ar_ap_engine: Any, memory: Any) -> str:
    parts = []
    try:
        overdue = ar_ap_engine.get_overdue_items()
        upcoming = ar_ap_engine.get_upcoming_due(days_ahead=7)
        overdue_r = len(overdue.get("receivables", []))
        overdue_p = len(overdue.get("payables", []))
        upcoming_p = len(upcoming.get("payables", []))
        if overdue_r or overdue_p or upcoming_p:
            parts.append(
                f"AR/AP snapshot: {overdue_r} overdue receivable(s), "
                f"{overdue_p} overdue payable(s), {upcoming_p} payable(s) due within 7 days."
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        budget_data = memory.load_budgets()
        budgets = budget_data.get("budgets", [])
        if budgets:
            parts.append(f"Active budgets: {len(budgets)} monthly budget(s) set.")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(parts)


def build_learned_context(memory: Any) -> str:
    entries = memory.load_learned_sources().get("entries", [])
    if not entries:
        return "No learned sources stored yet."
    lines = []
    for entry in entries[-6:]:
        domain = urlparse(entry.get("url", "")).netloc or "source"
        lines.append(
            f"- {entry.get('title', 'Untitled')} ({domain}): {entry.get('summary', '')[:280]}"
        )
    return "\n".join(lines)


def enrich_with_category(user_input: str, categorization: Any) -> str:
    lower = user_input.lower()
    is_transaction_intent = any(
        kw in lower for kw in ("record", "add", "log", "post", "expense", "income", "spent", "received", "paid")
    )
    if not is_transaction_intent:
        return user_input
    try:
        suggestion = categorization.suggest_category(user_input)
        if suggestion and suggestion.get("confidence", 0) >= 0.6:
            return (
                f"[Suggested category from local rules: {suggestion['category']} "
                f"(confidence {suggestion['confidence']:.0%})]\n{user_input}"
            )
    except Exception:  # noqa: BLE001
        pass
    return user_input


def build_messages(
    user_input: str,
    *,
    system_prompt: str,
    custom_rules: dict,
    memory: Any,
    ar_ap_engine: Any,
) -> list[dict[str, str]]:
    financial_context = build_financial_context(ar_ap_engine, memory)
    learned_context = build_learned_context(memory)
    business = memory.get_current_business()
    short_term = memory.load_short_term_context()
    custom_rules_str = json.dumps(custom_rules, indent=2)
    business_context = json.dumps(business, indent=2)
    short_term_context = json.dumps(short_term, indent=2)

    system_content = (
        f"{system_prompt}\n\n"
        "Custom correction rules that must be applied before every action:\n"
        f"{custom_rules_str}\n\n"
        "Current active business silo:\n"
        f"{business_context}\n\n"
        "Current short-term context:\n"
        f"{short_term_context}\n\n"
    )
    if financial_context:
        system_content += f"Current financial alerts:\n{financial_context}\n\n"
    system_content += f"Learned operating knowledge:\n{learned_context}"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_input},
    ]


def extract_action_plan(response_text: str) -> dict[str, Any]:
    text = re.sub(r"```(?:json)?\s*", "", response_text).strip().strip("`").strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "thought": "Model returned plain text; no tool action extracted.",
            "action": "respond",
            "parameters": {},
            "response": response_text.strip(),
        }


def parse_json_response(text: str) -> dict[str, Any] | None:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def self_reflect(
    user_input: str,
    draft_result: dict[str, Any],
    *,
    reflection_client: Any,
    memory: Any,
    custom_rules: dict,
) -> dict[str, Any]:
    reflection_prompt = [
        {
            "role": "system",
            "content": (
                "You are the CPA-Agent safety verifier. Review the proposed result for math mistakes, "
                "business silo leakage, unsupported tax claims, and risky accounting categorization. "
                "Respond only in JSON with keys approved, concerns, corrected_message."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "user_input": user_input,
                    "active_business": memory.get_current_business(),
                    "draft_result": draft_result,
                    "custom_rules": custom_rules,
                },
                indent=2,
            ),
        },
    ]
    reflection_text = reflection_client.chat(reflection_prompt)
    result = parse_json_response(reflection_text)
    if result is not None:
        return result
    return {
        "approved": False,
        "concerns": ["Reflection step returned malformed output."],
        "corrected_message": "I need a manual review before I confirm that action.",
    }
