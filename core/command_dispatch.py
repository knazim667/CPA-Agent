"""Domain-specific command handlers called from command_handler.py."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def _status_response(message: str, agent: Any) -> dict[str, Any]:
    return {"message": message, "status": agent.get_status(), "presentation": None}


def handle_split_command(split_cmd: dict, user_input: str, agent: Any) -> dict[str, Any]:
    try:
        rows = agent.categorization.split_transaction(
            split_cmd["total_amount"],
            split_cmd["splits"],
            date=date.today().isoformat(),
            parent_description=split_cmd["parent_description"],
        )
    except ValueError as exc:
        return _status_response(str(exc), agent)
    result = agent.record_bulk_transactions(rows)
    agent.memory.append_conversation_entry({"user_input": user_input, "outcome": {"message": result["message"]}})
    return _status_response(result["message"], agent)


def handle_budget_command(budget_cmd: dict, agent: Any) -> dict[str, Any]:
    if budget_cmd.get("list"):
        count = len(agent.memory.load_budgets().get("budgets", []))
        return _status_response(f"{count} budget(s) set.", agent)
    new_budget = agent.budget_engine.set_budget(
        category=budget_cmd["category"],
        amount=budget_cmd["amount"],
        period="monthly",
        business_key=agent.memory.current_business_key,
    )
    budget_data = agent.memory.load_budgets()
    budget_data["budgets"] = [
        b for b in budget_data["budgets"]
        if b.get("category", "").lower() != budget_cmd["category"].lower()
    ]
    budget_data["budgets"].append(new_budget)
    agent.memory.save_budgets(budget_data)
    return _status_response(
        f"Budget set — {new_budget['category']} · ${new_budget['amount']:.2f}/month.", agent
    )


def handle_recurring_command(recurring_cmd: dict, user_input: str, agent: Any) -> dict[str, Any]:
    import calendar as _cal
    if recurring_cmd.get("list"):
        schedules = agent.recurring.list_schedules()
        msg = f"{len(schedules)} recurring schedule(s) active." if schedules else "No recurring schedules."
        return _status_response(msg, agent)
    if recurring_cmd.get("cancel"):
        keyword = user_input.lower().replace("cancel", "").replace("recurring", "").strip()
        for s in agent.recurring.list_schedules():
            if keyword in s["description"].lower():
                agent.recurring.cancel_schedule(s["id"])
                agent._save_recurring()
                return _status_response(f"Cancelled recurring: {s['description']}.", agent)
        return _status_response("No matching recurring schedule found.", agent)
    today = date.today()
    day = recurring_cmd["day_of_period"]
    freq = recurring_cmd["frequency"]
    last_day = _cal.monthrange(today.year, today.month)[1]
    start = date(today.year, today.month, min(day, last_day)).isoformat()
    if start < today.isoformat():
        m2 = today.month % 12 + 1
        y2 = today.year if today.month < 12 else today.year + 1
        last2 = _cal.monthrange(y2, m2)[1]
        start = date(y2, m2, min(day, last2)).isoformat()
    cat = agent.categorization.suggest_category(recurring_cmd["description"])
    category = cat["category"] if cat else "Misc"
    freq_full = freq + "ly" if not freq.endswith("ly") else freq
    schedule = agent.recurring.create_schedule(
        description=recurring_cmd["description"],
        amount=recurring_cmd["amount"],
        category=category,
        entry_type=recurring_cmd["entry_type"],
        frequency=freq_full,
        day_of_period=day,
        start_date=start,
    )
    agent._save_recurring()
    return _status_response(
        f"Recurring set — {schedule['description']} · ${schedule['amount']:.2f} · "
        f"{schedule['entry_type']} · {schedule['frequency']} from {schedule['next_date']}.",
        agent,
    )


def handle_ar_ap_command(ar_ap_cmd: dict, user_input: str, agent: Any) -> dict[str, Any]:
    action = ar_ap_cmd.get("action")
    if action == "add_receivable":
        amount = ar_ap_cmd.get("amount")
        client_vendor = ar_ap_cmd.get("client_vendor")
        if amount is None or client_vendor is None:
            return _status_response(
                "I need both an amount and a client name to create a receivable. "
                "Please specify like: 'Add receivable $500 from ClientName'", agent
            )
        due_date = (date.today() + timedelta(days=30)).isoformat()
        agent.ar_ap_engine.add_receivable(
            client=client_vendor, amount=amount, due_date=due_date,
            notes=f"Created via voice command: {user_input}",
        )
        return _status_response(f"Created receivable for {client_vendor}: ${amount:.2f} due {due_date}", agent)
    if action == "add_payable":
        amount = ar_ap_cmd.get("amount")
        client_vendor = ar_ap_cmd.get("client_vendor")
        if amount is None or client_vendor is None:
            return _status_response(
                "I need both an amount and a vendor name to create a payable. "
                "Please specify like: 'Add payable $300 for VendorName'", agent
            )
        due_date = (date.today() + timedelta(days=30)).isoformat()
        agent.ar_ap_engine.add_payable(
            vendor=client_vendor, amount=amount, due_date=due_date,
            notes=f"Created via voice command: {user_input}",
        )
        return _status_response(f"Created payable for {client_vendor}: ${amount:.2f} due {due_date}", agent)
    if action == "mark_paid":
        entry_type = ar_ap_cmd.get("entry_type", "receivable")
        data = agent.ar_ap_engine.get_ar_ap()
        collection = "receivables" if entry_type == "receivable" else "payables"
        open_entries = [e for e in data[collection] if e["status"] == "open"]
        if not open_entries:
            return _status_response(f"No open {entry_type} entries found to mark as paid.", agent)
        latest_entry = max(open_entries, key=lambda x: x["issue_date"])
        paid_date = date.today().isoformat()
        agent.ar_ap_engine.mark_paid(entry_id=latest_entry["id"], entry_type=entry_type, paid_date=paid_date)
        description = (
            f"Invoice paid: {latest_entry['client_vendor']}"
            if entry_type == "receivable"
            else f"Bill paid: {latest_entry['client_vendor']}"
        )
        agent.record_structured_transaction(
            date=paid_date, description=description,
            category="Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
            amount=latest_entry["amount"],
            entry_type="Income" if entry_type == "receivable" else "Expense",
            notes=latest_entry.get("notes", ""),
        )
        return _status_response(
            f"Marked {entry_type} '{latest_entry['client_vendor']}' as paid and posted to ledger.", agent
        )
    if action == "list_ar_ap":
        data = agent.ar_ap_engine.get_ar_ap()
        r_count = len(data["receivables"])
        p_count = len(data["payables"])
        od_r = len([r for r in data["receivables"] if r["days_outstanding"] > 0 and r["status"] == "open"])
        od_p = len([p for p in data["payables"] if p["days_outstanding"] > 0 and p["status"] == "open"])
        return _status_response(
            f"AR/AP Summary: {r_count} receivables ({od_r} overdue), {p_count} payables ({od_p} overdue)", agent
        )
    if action == "get_overdue":
        overdue = agent.ar_ap_engine.get_overdue_items()
        r_count = len(overdue["receivables"])
        p_count = len(overdue["payables"])
        if r_count == 0 and p_count == 0:
            return _status_response("No overdue receivables or payables.", agent)
        parts = []
        if r_count > 0:
            parts.append(f"{r_count} overdue receivable(s)")
        if p_count > 0:
            parts.append(f"{p_count} overdue payable(s)")
        return _status_response(f"Overdue items: {', '.join(parts)}", agent)
    return _status_response("Unknown AR/AP action.", agent)


def handle_tax_command(tax_cmd: dict, agent: Any) -> dict[str, Any]:
    action = tax_cmd.get("action")
    if action == "get_tax_estimate":
        ledger_rows = agent.sheets.read_range(
            spreadsheet_id=agent.memory.get_current_business()["google_sheet_id"],
            range_name="Ledger!A:G",
        )
        tax_summary = agent.tax_engine.compute_tax_summary(ledger_rows)
        return _status_response(
            f"Tax Estimate: Net Income ${tax_summary['net_income']:.2f}, "
            f"SE Tax ${tax_summary['se_tax']:.2f}, "
            f"Federal Tax ${tax_summary['federal_tax']:.2f}, "
            f"Total Tax ${tax_summary['total_tax']:.2f}",
            agent,
        )
    if action == "get_tax_deadlines":
        deadlines = agent.tax_engine.get_irs_deadlines(date.today().year)
        deadline_strs = [f"{d['description']}: {d['deadline']}" for d in deadlines]
        return _status_response(f"Tax Deadlines: {', '.join(deadline_strs)}", agent)
    if action == "get_tax_alerts":
        alerts = agent.tax_engine.get_upcoming_alerts()
        if not alerts:
            return _status_response("No upcoming tax deadlines in the next 30 days.", agent)
        alert_strs = [f"{a['description']}: {a['deadline']} ({a['days_until']} days)" for a in alerts]
        return _status_response(f"Upcoming Tax Alerts: {', '.join(alert_strs)}", agent)
    return _status_response("Unknown tax action.", agent)


def handle_profile_command(cmd_lower: str, user_input: str, agent: Any) -> dict[str, Any] | None:
    if any(phrase in cmd_lower for phrase in [
        "what industry", "what is the industry", "what legal structure",
        "what accounting basis", "show profile", "business profile",
    ]):
        profile = agent.memory.load_business_profile(agent.memory.current_business_key)
        fields = {
            "Business Name": profile.get("business_name", ""),
            "Legal Structure": profile.get("legal_structure", "") or "Not set",
            "Industry": profile.get("industry", "") or "Not set",
            "Business Model": profile.get("business_model", "") or "Not set",
            "Accounting Basis": profile.get("accounting_basis", ""),
            "Inventory Method": profile.get("inventory_method", ""),
            "State": profile.get("state", ""),
            "EIN": profile.get("federal_ein", "") or "Not set",
        }
        lines = "\n".join(f"  {k}: {v}" for k, v in fields.items())
        return _status_response(
            f"Business profile for {profile.get('business_name', 'Unknown Business')}:\n{lines}", agent
        )
    if "set accounting basis" in cmd_lower or "change accounting basis" in cmd_lower:
        basis = "accrual" if "accrual" in cmd_lower else "cash"
        agent.memory.update_business_profile(agent.memory.current_business_key, {"accounting_basis": basis})
        return _status_response(f"Accounting basis updated to {basis}.", agent)
    if "set industry" in cmd_lower or "change industry" in cmd_lower:
        industries = [
            "e_commerce", "import_export", "professional_services", "retail",
            "construction", "healthcare", "content_creator", "manufacturing",
        ]
        matched = next((i for i in industries if i.replace("_", " ") in cmd_lower or i in cmd_lower), None)
        if matched:
            agent.memory.update_business_profile(agent.memory.current_business_key, {"industry": matched})
            return _status_response(f"Industry set to {matched}.", agent)
        return _status_response(
            "Industry not recognized. Valid options: " + ", ".join(industries), agent
        )
    if "set legal structure" in cmd_lower or "change legal structure" in cmd_lower or (
        ("s-corp" in cmd_lower or "s corp" in cmd_lower)
        and ("set" in cmd_lower or "change" in cmd_lower or "elect" in cmd_lower)
    ):
        structures = {
            "single_member_llc": ["single member", "single-member"],
            "multi_member_llc": ["multi member", "multi-member"],
            "s_corp": ["s-corp", "s corp", "scorp"],
            "partnership": ["partnership"],
            "sole_proprietor": ["sole proprietor"],
        }
        matched_struct = next(
            (key for key, aliases in structures.items() if any(a in cmd_lower for a in aliases)),
            None,
        )
        if matched_struct:
            agent.memory.update_business_profile(agent.memory.current_business_key, {"legal_structure": matched_struct})
            return _status_response(f"Legal structure updated to {matched_struct}.", agent)
        return _status_response(
            "Legal structure not recognized. Valid options: " + ", ".join(structures), agent
        )
    return None
