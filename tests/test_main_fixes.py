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


def test_research_tax_action():
    from unittest.mock import patch
    from skills.tax_researcher import TaxResearchResult
    agent = make_agent()
    agent.memory.record_learned_source = MagicMock()
    fake = TaxResearchResult(url="https://irs.gov", title="IRS Update", summary="Standard deduction raised.")
    plan = {"action": "research_tax", "parameters": {"url": "https://irs.gov"}, "response": ""}
    with patch("skills.tax_researcher.fetch_tax_update", return_value=fake):
        result = agent.execute_action(plan, "research tax")
    assert result["status"] == "success"
    assert "IRS Update" in result["message"]
    agent.memory.record_learned_source.assert_called_once()


def test_research_tax_requires_url():
    agent = make_agent()
    plan = {"action": "research_tax", "parameters": {}, "response": ""}
    assert agent.execute_action(plan, "tax")["status"] == "needs_review"


# ── Bug 3: Duplicate transaction detection ────────────────────────────────────

def test_find_duplicate_row_returns_match(mocker):
    from skills.google_sheets_manager import GoogleSheetsManager
    mgr = GoogleSheetsManager.__new__(GoogleSheetsManager)
    mocker.patch.object(
        mgr,
        "read_range",
        return_value=[
            ["2026-04-27", "Coffee", "Meals", "12.5", "Expense", "", ""],
            ["2026-04-26", "Rent", "Rent", "1500.0", "Expense", "", ""],
        ],
    )
    result = mgr.find_duplicate_row("sheet_id", "2026-04-27", "12.5", "Expense")
    assert result is not None
    assert result["description"] == "Coffee"


def test_find_duplicate_row_returns_none_when_no_match(mocker):
    from skills.google_sheets_manager import GoogleSheetsManager
    mgr = GoogleSheetsManager.__new__(GoogleSheetsManager)
    mocker.patch.object(mgr, "read_range", return_value=[
        ["2026-04-26", "Rent", "Rent", "1500.0", "Expense", "", ""],
    ])
    result = mgr.find_duplicate_row("sheet_id", "2026-04-27", "999.0", "Income")
    assert result is None


def test_find_duplicate_row_skips_short_rows(mocker):
    from skills.google_sheets_manager import GoogleSheetsManager
    mgr = GoogleSheetsManager.__new__(GoogleSheetsManager)
    mocker.patch.object(mgr, "read_range", return_value=[["2026-04-27", "Partial"]])
    result = mgr.find_duplicate_row("sheet_id", "2026-04-27", "12.5", "Expense")
    assert result is None


# ── Bug 4: OCR graceful fallback ──────────────────────────────────────────────

def test_ocr_returns_message_when_pytesseract_missing(tmp_path, mocker):
    import skills.document_processor as dp
    mocker.patch.object(dp, "_PYTESSERACT_INSTALLED", False)
    processor = dp.DocumentProcessor(tmp_path)
    from PIL import Image
    img_path = tmp_path / "receipt.png"
    Image.new("RGB", (10, 10), color="white").save(img_path)
    result = processor.extract_document(img_path)
    assert "OCR unavailable" in result["text"]


def test_ocr_returns_message_when_tesseract_binary_missing(tmp_path, mocker):
    import skills.document_processor as dp
    mocker.patch.object(dp, "_PYTESSERACT_INSTALLED", True)
    mocker.patch("shutil.which", return_value=None)
    processor = dp.DocumentProcessor(tmp_path)
    from PIL import Image
    img_path = tmp_path / "receipt.png"
    Image.new("RGB", (10, 10), color="white").save(img_path)
    result = processor.extract_document(img_path)
    assert "OCR unavailable" in result["text"]


# ── detect_split_command ───────────────────────────────────────────────────────


def test_detect_split_command_happy_path():
    agent = make_agent()
    result = agent.detect_split_command(
        "split this $200 Amazon charge: $100 office supplies, $100 inventory"
    )
    assert result is not None
    assert result["total_amount"] == 200.0
    assert result["parent_description"] == "Amazon charge"
    assert len(result["splits"]) == 2
    assert result["splits"][0]["amount"] == 100.0
    assert result["splits"][0]["category"] == "Office Supplies"
    assert result["splits"][1]["category"] == "Inventory"


def test_detect_split_command_three_way_split():
    agent = make_agent()
    result = agent.detect_split_command(
        "split $300 Amazon: $150 supplies, $100 equipment, $50 meals"
    )
    assert result is not None
    assert len(result["splits"]) == 3


def test_detect_split_command_with_comma_amount():
    agent = make_agent()
    result = agent.detect_split_command(
        "split this $1,500 contractor invoice: $900 labor, $600 materials"
    )
    assert result is not None
    assert result["total_amount"] == 1500.0
    assert len(result["splits"]) == 2


def test_detect_split_command_no_match():
    agent = make_agent()
    assert agent.detect_split_command("record $200 office supplies") is None


def test_detect_split_command_amounts_parsed_as_floats():
    agent = make_agent()
    result = agent.detect_split_command(
        "split $100 Staples: $75.50 supplies, $24.50 equipment"
    )
    assert result is not None
    assert isinstance(result["splits"][0]["amount"], float)
    assert result["splits"][0]["amount"] == 75.50
