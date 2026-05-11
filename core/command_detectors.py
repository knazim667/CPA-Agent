"""Pure string-parsing functions that classify user commands. No I/O, no side effects."""
from __future__ import annotations

import re


def detect_business_switch(user_input: str) -> str | None:
    match = re.search(r"switch to ([a-zA-Z0-9_ -]+)", user_input, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def detect_business_rename(user_input: str) -> str | None:
    patterns = (
        r"(?:rename|change)\s+(?:the\s+)?(?:current\s+)?business(?:\s+\w+)?\s+to\s+([A-Za-z0-9 _-]+)",
        r"update\s+(?:the\s+)?business\s+name\s+to\s+([A-Za-z0-9 _-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .")
    return None


def detect_business_creation(user_input: str) -> str | None:
    patterns = (
        r"(?:i\s+(?:started|launched|opened)|we\s+(?:started|launched|opened))\s+(?:a\s+)?(?:new\s+)?business(?:\s+called|\s+named)?\s+([A-Za-z0-9][A-Za-z0-9 &._-]*)",
        r"(?:create|add|set\s+up|setup)\s+(?:a\s+)?(?:new\s+)?business(?:\s+called|\s+named)?\s+([A-Za-z0-9][A-Za-z0-9 &._-]*)",
        r"(?:create|add)\s+business\s+([A-Za-z0-9][A-Za-z0-9 &._-]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" .")
            candidate = re.sub(r"\s+(please|for me|now)$", "", candidate, flags=re.IGNORECASE)
            if candidate:
                return candidate
    return None


def extract_learning_urls(user_input: str) -> list[str]:
    return re.findall(r"https?://[^\s)]+", user_input)


def is_learning_request(user_input: str) -> bool:
    lowered = user_input.lower()
    markers = ("learn", "study", "read this", "use this doc", "research this", "for the agent")
    return any(marker in lowered for marker in markers)


def is_recalculation_request(user_input: str) -> bool:
    lowered = user_input.lower()
    markers = ("re-check", "recheck", "recalculate", "fix the accounts", "check for errors", "fix if there is error")
    return any(marker in lowered for marker in markers)


def detect_recurring_command(user_input: str) -> dict | None:
    lower = user_input.lower()
    m = re.search(
        r"schedule\s+(.+?)\s+\$?([\d,]+(?:\.\d{1,2})?)\s+(expense|income)\s+on\s+the\s+(\d+)(?:st|nd|rd|th)?\s+every\s+(\w+)",
        lower,
    )
    if m:
        return {
            "description": m.group(1).strip().title(),
            "amount": float(m.group(2).replace(",", "")),
            "entry_type": m.group(3).title(),
            "day_of_period": int(m.group(4)),
            "frequency": m.group(5).rstrip("s"),
        }
    if "cancel" in lower and "recurring" in lower:
        return {"cancel": True, "raw": user_input}
    if ("show" in lower or "list" in lower) and "recurring" in lower:
        return {"list": True}
    return None


def detect_budget_command(user_input: str) -> dict | None:
    lower = user_input.lower()
    m = re.search(
        r"(?:set\s+)?(?P<cat>[a-z &]+?)\s+budget\s+\$?([\d,]+(?:\.\d{1,2})?)\s+(?:per\s+month|monthly|a\s+month)",
        lower,
    )
    if m:
        return {
            "category": m.group("cat").strip().title(),
            "amount": float(m.group(2).replace(",", "")),
        }
    if ("show" in lower or "list" in lower) and "budget" in lower:
        return {"list": True}
    return None


def detect_reconcile_command(user_input: str) -> dict | None:
    lower = user_input.lower()
    if "reconcile" in lower and ("bank" in lower or "statement" in lower or "csv" in lower):
        return {"action": "reconcile"}
    return None


def detect_ar_ap_command(user_input: str) -> dict | None:
    lower = user_input.lower()
    is_add = ("add" in lower or "create" in lower or "new" in lower)
    is_ar_keyword = ("receivable" in lower or "invoice" in lower or "owed" in lower)
    is_ap_keyword = ("bill" in lower or "payable" in lower)
    if is_add and (is_ar_keyword or is_ap_keyword):
        amount_match = re.search(r'\$?([\d,]+\.?\d*)', user_input)
        amount = float(amount_match.group(1).replace(',', '')) if amount_match else None
        cv_match = re.search(r'(?:from|for|to)\s+([A-Za-z0-9\s&]+?)(?:\s+\$|$)', lower)
        client_vendor = cv_match.group(1).strip().title() if cv_match else None
        action = "add_receivable" if is_ar_keyword else "add_payable"
        return {"action": action, "amount": amount, "client_vendor": client_vendor}
    if ("mark" in lower or "payment" in lower or "paid" in lower) and (is_ar_keyword or is_ap_keyword):
        entry_type = "receivable" if is_ar_keyword else "payable"
        return {"action": "mark_paid", "entry_type": entry_type}
    if ("show" in lower or "list" in lower or "get" in lower) and (is_ar_keyword or is_ap_keyword or "ar" in lower or "ap" in lower or "accounts" in lower):
        return {"action": "list_ar_ap"}
    if "overdue" in lower or "late" in lower:
        return {"action": "get_overdue"}
    return None


def detect_tax_command(user_input: str) -> dict | None:
    lower = user_input.lower()
    if ("tax" in lower or "owe" in lower) and ("estimate" in lower or "calculate" in lower or "owe" in lower or "payment" in lower):
        return {"action": "get_tax_estimate"}
    if ("deadline" in lower or "due" in lower) and ("tax" in lower or "irs" in lower):
        return {"action": "get_tax_deadlines"}
    if ("alert" in lower or "reminder" in lower or "upcoming" in lower) and "tax" in lower:
        return {"action": "get_tax_alerts"}
    return None


def detect_delete_command(user_input: str) -> dict | None:
    lower = user_input.lower()
    duplicate_words = ("duplicate", "duplicates", "dupes", "dupe")
    delete_words = ("delete", "remove", "clean", "clear", "deduplicate", "dedupe", "fix", "purge")
    if any(d in lower for d in duplicate_words) and any(w in lower for w in delete_words):
        return {"action": "delete_duplicates"}
    if "clean up" in lower and ("ledger" in lower or "transactions" in lower or "entries" in lower):
        return {"action": "delete_duplicates"}
    return None


def detect_split_command(user_input: str) -> dict | None:
    if "split" not in user_input.lower():
        return None
    m = re.search(
        r"split\s+(?:this\s+)?\$?([\d,]+(?:\.\d{1,2})?)\s+([^:]+):\s*(.+)",
        user_input,
        re.IGNORECASE,
    )
    if not m:
        return None
    total = float(m.group(1).replace(",", ""))
    parent_desc = m.group(2).strip()
    splits = []
    for sm in re.finditer(r"\$?(\d[\d,]*(?:\.\d{1,2})?)\s+([^,$]+)", m.group(3)):
        label = sm.group(2).strip().rstrip(".,;:!?")
        if not label:
            continue
        splits.append({
            "amount": float(sm.group(1).replace(",", "")),
            "category": label.title(),
            "description": f"{parent_desc} - {label}",
        })
    return (
        {"total_amount": total, "parent_description": parent_desc, "splits": splits}
        if splits
        else None
    )
