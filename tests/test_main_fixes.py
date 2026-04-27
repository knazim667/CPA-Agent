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
