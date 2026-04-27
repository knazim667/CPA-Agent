from __future__ import annotations
from unittest.mock import MagicMock, patch


def make_agent():
    with (
        patch("main.MemoryManager"),
        patch("main.get_model_client"),
        patch("main.GoogleSheetsManager"),
        patch("main.GoogleDocsManager"),
        patch("main.KnowledgeManager"),
        patch("main.sr.Recognizer"),
        patch("main.sr.Microphone", side_effect=OSError),
    ):
        from main import CPAAgent
        agent = CPAAgent.__new__(CPAAgent)
        agent.memory = MagicMock()
        agent.memory.current_business_key = "biz_a"
        agent.workspace_boot_error = None
        return agent


def test_date_inference_single_date():
    agent = make_agent()
    result = agent._infer_dates_from_text("I bought supplies on 01/15/2026")
    assert result.get("default") == "01/15/2026"


def test_date_inference_no_hardcoded_keywords():
    agent = make_agent()
    result = agent._infer_dates_from_text("nozzle on 01/10/2026 filament on 01/20/2026")
    assert "nozzle" not in result
    assert "filament" not in result
    assert result.get("default") == "01/20/2026"


def test_bulk_values_generic_business():
    agent = make_agent()
    user_input = "Office chair: $350\nDesk lamp: $45\nKeyboard: $120"
    params = {"category": "Furniture", "type": "Expense", "date": "04/01/2026"}
    rows = agent._infer_bulk_values_from_user_input(user_input, params)
    assert len(rows) == 3
    assert "Office chair" in [r[1] for r in rows]


def test_dashboard_reads_beyond_50_rows():
    agent = make_agent()
    many_rows = [["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]]
    for i in range(60):
        many_rows.append([f"2026-01-{(i % 28) + 1:02d}", f"Item {i}", "Office", "10.00", "Expense", "", ""])
    agent.sheets = MagicMock()
    agent.sheets.read_range.return_value = many_rows
    agent.memory.get_current_business.return_value = {"google_sheet_id": "sheet-id", "business_name": "Biz"}
    agent.memory.load_skill_memory.return_value = {"history": []}
    agent.memory.load_transaction_audit.return_value = {"entries": []}
    agent.memory.load_short_term_context.return_value = {"conversation": []}
    snapshot = agent.get_dashboard_snapshot()
    call_args = agent.sheets.read_range.call_args
    assert "A1:G50" not in str(call_args)
    assert snapshot["transaction_count"] == 60


def test_calculate_payroll_action():
    agent = make_agent()
    plan = {"action": "calculate_payroll", "parameters": {"gross_pay": 5000.0, "federal_rate": 0.12}, "response": ""}
    result = agent.execute_action(plan, "payroll")
    assert result["status"] == "success"
    assert result["details"]["gross_pay"] == 5000.0
    assert result["details"]["net_pay"] == round(5000 - 310 - 72.5 - 600, 2)


def test_calculate_payroll_rejects_zero_gross():
    agent = make_agent()
    plan = {"action": "calculate_payroll", "parameters": {"gross_pay": 0}, "response": ""}
    assert agent.execute_action(plan, "payroll")["status"] == "needs_review"
