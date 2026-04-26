# CPA-Agent Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenRouter as a fourth model provider, fix backend bugs and stub integrations, add P&L/CSV/ledger endpoints, and redesign the UI with a clean modern light theme and tabbed navigation.

**Architecture:** Backend-first (Tasks 1-12) then full UI rewrite (Tasks 13-15). New endpoints follow the existing FastAPI pattern in `web_app.py`. UI is a full rewrite of three files only — no new frontend dependencies.

**Tech Stack:** Python 3.14, FastAPI, pytest, `requests` (HTTP), Google Sheets API, Vanilla JS (ES2020), CSS custom properties.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tests/conftest.py` | Create | Shared pytest fixtures |
| `tests/test_openrouter_client.py` | Create | Unit tests for OpenRouter client |
| `tests/test_model_client.py` | Create | Unit tests for provider routing |
| `tests/test_main_fixes.py` | Create | Unit tests for date inference + payroll + tax actions |
| `tests/test_web_app.py` | Create | Integration tests for all new/changed endpoints |
| `core/openrouter_client.py` | Create | OpenRouter HTTP client |
| `core/model_client.py` | Modify | Add openrouter branch |
| `main.py` | Modify | Fix date inference, fix row limit, add payroll + tax actions |
| `web_app.py` | Modify | Fix memory leak, add /api/provider, /api/report/pl, /api/export/csv, /api/ledger |
| `requirements.txt` | Modify | Add pytest, pytest-mock |
| `ui/index.html` | Rewrite | Tabbed layout with top bar |
| `ui/styles.css` | Rewrite | Clean modern light design system |
| `ui/app.js` | Rewrite | Tab router, toast, skeleton, P&L, CSV, settings slide-over |

---

## Task 1: Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest to requirements.txt**

Append to `requirements.txt`:
```
pytest>=8.0.0
pytest-mock>=3.14.0
```

- [ ] **Step 2: Install the new dependencies**

```bash
cd /Users/muhammadnazam/Documents/CPA-Agent
source .venv/bin/activate
pip install pytest pytest-mock
```

Expected: `Successfully installed pytest-... pytest-mock-...`

- [ ] **Step 3: Create tests package and conftest**

```bash
touch tests/__init__.py
```

Create `tests/conftest.py`:
```python
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "MODEL_PROVIDER", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
        "OPENAI_API_KEY", "OPENAI_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL",
        "OLLAMA_MODEL", "OLLAMA_QUALITY_MODEL", "OLLAMA_REFLECTION_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def sample_ledger_rows():
    return [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Client payment", "Sales", "5000.00", "Income", "INV-001", ""],
        ["2026-01-15", "Office supplies", "Office", "200.00", "Expense", "REC-001", ""],
        ["2026-02-01", "Software sub", "Software", "50.00", "Expense", "REC-002", ""],
    ]
```

- [ ] **Step 4: Verify pytest runs without errors**

```bash
pytest tests/ --collect-only 2>&1 | head -20
```

Expected: zero tests collected, no import errors.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/
git commit -m "test: add pytest infrastructure and conftest fixtures"
```

---

## Task 2: OpenRouter Client

**Files:**
- Create: `core/openrouter_client.py`
- Create: `tests/test_openrouter_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_openrouter_client.py`:
```python
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest


def test_chat_sends_correct_headers(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    from core.openrouter_client import OpenRouterClient
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    mock_response.raise_for_status = MagicMock()
    with patch("requests.post", return_value=mock_response) as mock_post:
        client = OpenRouterClient()
        result = client.chat([{"role": "user", "content": "hi"}])
    assert result == "hello"
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["HTTP-Referer"] == "http://localhost:8000"
    assert headers["X-Title"] == "CPA-Agent"
    assert mock_post.call_args.kwargs["json"]["model"] == "nvidia/nemotron-3-super-120b-a12b:free"


def test_chat_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from core.openrouter_client import OpenRouterClient
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterClient().chat([{"role": "user", "content": "hi"}])


def test_default_model_is_nemotron(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    from core.openrouter_client import OpenRouterClient
    assert OpenRouterClient().model == "nvidia/nemotron-3-super-120b-a12b:free"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_openrouter_client.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'core.openrouter_client'`

- [ ] **Step 3: Implement `core/openrouter_client.py`**

```python
from __future__ import annotations

import os
from typing import Any

import requests


class OpenRouterClient:
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, timeout: int = 120) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "CPA-Agent",
            "Content-Type": "application/json",
        }
        response = requests.post(
            f"{self.BASE_URL}/chat/completions",
            headers=headers,
            json={"model": self.model, "messages": messages},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_openrouter_client.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add core/openrouter_client.py tests/test_openrouter_client.py
git commit -m "feat: add OpenRouter client with nemotron default model"
```

---

## Task 3: Extend model_client.py for OpenRouter

**Files:**
- Modify: `core/model_client.py`
- Create: `tests/test_model_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_model_client.py`:
```python
from __future__ import annotations
from unittest.mock import patch


def test_openrouter_provider_returns_openrouter_client(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("core.model_client.OpenRouterClient") as mock_cls:
        import importlib, core.model_client
        importlib.reload(core.model_client)
        from core.model_client import get_model_client
        get_model_client(purpose="reasoning", reasoning_mode="fast")
    mock_cls.assert_called_once()


def test_openai_provider_returns_openai_client(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    with patch("core.model_client.OpenAIClient") as mock_cls:
        import importlib, core.model_client
        importlib.reload(core.model_client)
        from core.model_client import get_model_client
        get_model_client(purpose="reasoning", reasoning_mode="fast")
    mock_cls.assert_called_once()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_model_client.py::test_openrouter_provider_returns_openrouter_client -v
```

Expected: `FAILED` — openrouter branch does not exist yet.

- [ ] **Step 3: Replace `core/model_client.py`**

```python
from __future__ import annotations

import os

from core.gemini_client import GeminiClient
from core.ollama_client import OllamaClient
from core.openai_client import OpenAIClient
from core.openrouter_client import OpenRouterClient


def get_model_client(*, purpose: str = "reasoning", reasoning_mode: str = "fast"):
    provider = os.getenv("MODEL_PROVIDER", "ollama").strip().lower()

    if provider == "openai":
        return OpenAIClient()
    if provider == "gemini":
        return GeminiClient()
    if provider == "openrouter":
        return OpenRouterClient()

    # Default: Ollama with multi-model support
    if purpose == "reflection":
        reflection_model = os.getenv("OLLAMA_REFLECTION_MODEL") or os.getenv("OLLAMA_AUDIT_MODEL")
        if reflection_model:
            return OllamaClient(model=reflection_model)
    if reasoning_mode == "quality":
        quality_model = os.getenv("OLLAMA_QUALITY_MODEL")
        if quality_model:
            return OllamaClient(model=quality_model)
    return OllamaClient()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_model_client.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add core/model_client.py tests/test_model_client.py
git commit -m "feat: add openrouter branch to model_client provider routing"
```

---

## Task 4: Fix Brittle Date Inference

**Files:**
- Modify: `main.py` (methods `_infer_dates_from_text` around line 856, `_infer_bulk_values_from_user_input` around line 808)
- Create: `tests/test_main_fixes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_fixes.py`:
```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_main_fixes.py::test_date_inference_no_hardcoded_keywords -v
```

Expected: `FAILED` — `nozzle` key will be present in the current implementation.

- [ ] **Step 3: Replace `_infer_dates_from_text` and `_infer_bulk_values_from_user_input` in `main.py`**

Find `_infer_dates_from_text` (around line 856) and replace it:
```python
def _infer_dates_from_text(self, text: str) -> dict[str, str]:
    mappings: dict[str, str] = {}
    all_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
    if not all_dates:
        return mappings
    mappings["default"] = all_dates[-1]
    for match in re.finditer(
        r"(?P<label>[A-Za-z0-9 /]+?)\s+(?:is on|on|dated)\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})",
        text,
        re.IGNORECASE,
    ):
        mappings[match.group("label").strip().lower()] = match.group("date")
    return mappings
```

Find `_infer_bulk_values_from_user_input` (around line 808) and replace it:
```python
def _infer_bulk_values_from_user_input(self, user_input: str, parameters: dict[str, Any]) -> list[list[Any]]:
    lines = [line.strip(" -\t") for line in user_input.splitlines() if line.strip()]
    extracted_items: list[tuple[str, float]] = []
    for line in lines:
        match = re.match(r"(.+?)\s*[:\-]\s*\$?([0-9]+(?:\.[0-9]{1,2})?)$", line)
        if match:
            extracted_items.append((match.group(1).strip(), float(match.group(2))))
    if not extracted_items:
        return []
    default_category = parameters.get("category") or parameters.get("account") or "Start-up Costs"
    entry_type = parameters.get("type") or parameters.get("entry_type") or "Expense"
    date_map = self._infer_dates_from_text(user_input)
    fallback_date = parameters.get("date") or date_map.get("default") or ""
    text_lines = user_input.splitlines()
    rows = []
    for description, amount in extracted_items:
        matched_date = fallback_date
        desc_line_idx = next(
            (i for i, line in enumerate(text_lines) if description.lower() in line.lower()), -1
        )
        if desc_line_idx >= 0 and len(date_map) > 1:
            preceding = "\n".join(text_lines[: desc_line_idx + 1])
            preceding_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", preceding)
            if preceding_dates:
                matched_date = preceding_dates[-1]
        for label, label_date in date_map.items():
            if label != "default" and label in description.lower():
                matched_date = label_date
                break
        rows.append(self._normalize_row([matched_date, description, default_category, amount, entry_type, "", parameters.get("notes", "")]))
    return rows
```

- [ ] **Step 4: Run all date inference tests**

```bash
pytest tests/test_main_fixes.py -v -k "date or bulk"
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main_fixes.py
git commit -m "fix: replace hardcoded date inference keywords with generic proximity matching"
```

---

## Task 5: Fix Ledger Row Limit

**Files:**
- Modify: `main.py` -> `get_dashboard_snapshot()` around line 665

- [ ] **Step 1: Add test to `tests/test_main_fixes.py`**

Append:
```python
def test_dashboard_reads_beyond_50_rows():
    agent = make_agent()
    many_rows = [["Date", "Desc", "Cat", "Amount", "Type", "Ref", "Notes"]]
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
    assert "A1:G50" not in call_args.kwargs.get("range_name", "")
    assert snapshot["transaction_count"] == 60
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_main_fixes.py::test_dashboard_reads_beyond_50_rows -v
```

Expected: `FAILED`

- [ ] **Step 3: Fix the range in `get_dashboard_snapshot` in `main.py`**

Find (around line 665):
```python
range_name="Ledger!A1:G50",
```
Change to:
```python
range_name="Ledger!A1:G",
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_main_fixes.py::test_dashboard_reads_beyond_50_rows -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "fix: remove 50-row ledger cap, use open-ended Sheets range"
```

---

## Task 6: Wire Payroll Action

**Files:**
- Modify: `main.py` -> `execute_action()` around line 337 (before the final return)

- [ ] **Step 1: Add test to `tests/test_main_fixes.py`**

Append:
```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_main_fixes.py -k "payroll" -v
```

Expected: `FAILED`

- [ ] **Step 3: Insert payroll branch into `execute_action` in `main.py`**

Insert before the final `return` statement in `execute_action` (the `return {"status": "success", "message": plan.get("response"...` block):
```python
        if action == "calculate_payroll":
            from skills.payroll_engine import calculate_simple_payroll
            gross_pay = self._safe_float(parameters.get("gross_pay", 0))
            federal_rate = float(parameters.get("federal_rate", 0.12))
            if gross_pay <= 0:
                return {"status": "needs_review", "message": "Gross pay must be a positive number.", "details": {"parameters": parameters}}
            calc = calculate_simple_payroll(gross_pay=gross_pay, federal_rate=federal_rate)
            return {
                "status": "success",
                "message": f"Payroll: Gross ${calc.gross_pay:.2f} | Federal ${calc.federal_withholding:.2f} | SS ${calc.social_security:.2f} | Medicare ${calc.medicare:.2f} | Net ${calc.net_pay:.2f}.",
                "details": {"gross_pay": calc.gross_pay, "federal_withholding": calc.federal_withholding, "social_security": calc.social_security, "medicare": calc.medicare, "net_pay": calc.net_pay},
            }
```

- [ ] **Step 4: Run payroll tests**

```bash
pytest tests/test_main_fixes.py -k "payroll" -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: wire calculate_payroll action into agent execute_action"
```

---

## Task 7: Wire Tax Researcher Action

**Files:**
- Modify: `main.py` -> `execute_action()` (after payroll block)

- [ ] **Step 1: Add test to `tests/test_main_fixes.py`**

Append:
```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_main_fixes.py -k "research_tax" -v
```

Expected: `FAILED`

- [ ] **Step 3: Insert tax research branch into `execute_action` in `main.py`**

Insert after the payroll block, before the final return:
```python
        if action == "research_tax":
            from skills.tax_researcher import fetch_tax_update
            url = parameters.get("url", "").strip()
            if not url:
                return {"status": "needs_review", "message": "A URL is required for tax research.", "details": {}}
            result = fetch_tax_update(url)
            self.memory.record_learned_source({"url": result.url, "title": result.title, "summary": result.summary, "topic": "tax"})
            return {"status": "success", "message": f"Tax research complete. Stored: {result.title}", "details": {"url": result.url, "title": result.title, "summary": result.summary}}
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: wire research_tax action into agent, stores result in learned sources"
```

---

## Task 8: Fix Document Draft Memory Leak

**Files:**
- Modify: `web_app.py`

- [ ] **Step 1: Add `import time` and the eviction helper to `web_app.py`**

Ensure `import os` and `import time` are in the imports at the top of `web_app.py`. Then after the `pending_document_drafts` dict declaration, add:

```python
_DRAFT_TTL_SECONDS = 3600
_DRAFT_MAX_ENTRIES = 100


def _evict_stale_drafts() -> None:
    now = time.time()
    stale = [k for k, v in pending_document_drafts.items() if now - v.get("created_at", 0) > _DRAFT_TTL_SECONDS]
    for k in stale:
        pending_document_drafts.pop(k, None)
    if len(pending_document_drafts) > _DRAFT_MAX_ENTRIES:
        oldest = sorted(pending_document_drafts.items(), key=lambda x: x[1].get("created_at", 0))
        for k, _ in oldest[: len(pending_document_drafts) - _DRAFT_MAX_ENTRIES]:
            pending_document_drafts.pop(k, None)
```

- [ ] **Step 2: Add `created_at` when storing a draft in `upload_document`**

Find the block (around line 209):
```python
pending_document_drafts[token] = {
    "business_key": agent.memory.current_business_key,
    "rows": draft["details"]["rows"],
    "file_name": extracted["file_name"],
    "instruction": instruction,
}
```

Replace with:
```python
_evict_stale_drafts()
pending_document_drafts[token] = {
    "business_key": agent.memory.current_business_key,
    "rows": draft["details"]["rows"],
    "file_name": extracted["file_name"],
    "instruction": instruction,
    "created_at": time.time(),
}
```

- [ ] **Step 3: Call `_evict_stale_drafts()` in `approve_document_draft`**

At the top of the `approve_document_draft` function body, before the `draft = pending_document_drafts.get(token)` line, add:
```python
_evict_stale_drafts()
```

- [ ] **Step 4: Verify import compiles**

```bash
source .venv/bin/activate
python -c "import web_app; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add web_app.py
git commit -m "fix: add TTL eviction and max-entry cap to pending_document_drafts"
```

---

## Task 9: Add POST /api/provider Endpoint

**Files:**
- Modify: `web_app.py`
- Create: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_app.py`:
```python
from __future__ import annotations
import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    memory_root = tmp_path / "memory"
    biz_dir = memory_root / "long_term" / "biz_a"
    biz_dir.mkdir(parents=True)
    (biz_dir / "config.json").write_text(
        '{"business_name":"Biz A","google_sheet_id":"","google_doc_id":"","state":"","default_books_currency":"USD","federal_ein":"","local_memory_db":""}',
        encoding="utf-8",
    )
    (memory_root / "active_business.json").write_text('{"active_business":"biz_a"}', encoding="utf-8")
    (memory_root / "short_term.json").write_text('{"conversation":[]}', encoding="utf-8")
    (memory_root / "skill_memory.json").write_text('{"history":[],"success_patterns":[],"failure_patterns":[]}', encoding="utf-8")
    (memory_root / "transaction_audit.json").write_text('{"entries":[]}', encoding="utf-8")
    (memory_root / "knowledge").mkdir()
    (memory_root / "knowledge" / "learned_sources.json").write_text('{"entries":[]}', encoding="utf-8")

    mock_agent = MagicMock()
    mock_agent.workspace_boot_error = None
    mock_agent.input_mode = "text"
    mock_agent.memory = MagicMock()
    mock_agent.memory.current_business_key = "biz_a"
    mock_agent.get_status.return_value = {
        "active_business_key": "biz_a",
        "active_business": {"business_name": "Biz A", "google_sheet_id": "", "google_doc_id": "", "state": ""},
        "businesses": [{"key": "biz_a", "business_name": "Biz A"}],
        "conversation": [], "workspace_boot_error": None, "input_mode": "text",
        "model_config": {"provider": "ollama", "reasoning_mode": "fast", "reasoning_model": "gpt-oss:20b", "reflection_model": "gpt-oss:20b"},
        "dashboard": {"transaction_count": 0, "income_total": 0.0, "expense_total": 0.0, "flagged_actions": 0, "recent_transactions": [], "recent_audits": []},
        "learned_source_count": 0,
    }

    import importlib, web_app
    web_app.agent = mock_agent
    importlib.reload(web_app)
    web_app.agent = mock_agent
    from web_app import app
    yield TestClient(app)


def test_provider_switch_to_openrouter(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    response = client.post("/api/provider", json={"provider": "openrouter"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_provider_switch_rejects_invalid(client):
    response = client.post("/api/provider", json={"provider": "banana"})
    assert response.status_code == 400


def test_provider_switch_to_openai(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = client.post("/api/provider", json={"provider": "openai"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web_app.py::test_provider_switch_to_openrouter -v
```

Expected: `FAILED` — 404

- [ ] **Step 3: Add Pydantic model and endpoint to `web_app.py`**

After the `ModelModeRequest` class, add:
```python
class ProviderRequest(BaseModel):
    provider: str
```

After the `set_model_mode` endpoint, add:
```python
@app.post("/api/provider")
def set_provider(payload: ProviderRequest) -> dict[str, Any]:
    provider = payload.provider.strip().lower()
    valid_providers = {"ollama", "openai", "gemini", "openrouter"}
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {', '.join(sorted(valid_providers))}.")
    with agent_lock:
        os.environ["MODEL_PROVIDER"] = provider
        agent._refresh_model_clients()
        return {"ok": True, "message": f"Provider switched to {provider}.", "status": agent.get_status()}
```

Make sure `import os` is at the top of `web_app.py`.

- [ ] **Step 4: Run provider tests**

```bash
pytest tests/test_web_app.py -k "provider" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add web_app.py tests/test_web_app.py
git commit -m "feat: add POST /api/provider endpoint for runtime provider switching"
```

---

## Task 10: Add GET /api/report/pl Endpoint

**Files:**
- Modify: `web_app.py`

- [ ] **Step 1: Add tests to `tests/test_web_app.py`**

Append:
```python
def test_pl_report_returns_category_totals(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Client A", "Consulting", "5000.00", "Income", "", ""],
        ["2026-01-15", "Supplies", "Office", "200.00", "Expense", "", ""],
        ["2026-02-01", "Software", "SaaS", "50.00", "Expense", "", ""],
    ]
    with patch("web_app.agent.sheets.read_range", return_value=rows):
        with patch("web_app.agent.memory.get_current_business", return_value={"business_name": "Biz A", "google_sheet_id": "sheet-id"}):
            response = client.get("/api/report/pl")
    assert response.status_code == 200
    data = response.json()
    assert data["income_total"] == 5000.0
    assert data["expense_total"] == 250.0
    assert data["net"] == 4750.0


def test_pl_report_date_filter(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Jan sale", "Sales", "1000.00", "Income", "", ""],
        ["2026-03-05", "Mar sale", "Sales", "2000.00", "Income", "", ""],
    ]
    with patch("web_app.agent.sheets.read_range", return_value=rows):
        with patch("web_app.agent.memory.get_current_business", return_value={"business_name": "Biz A", "google_sheet_id": "sheet-id"}):
            response = client.get("/api/report/pl?from_date=2026-02-01")
    assert response.json()["income_total"] == 2000.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web_app.py -k "pl_report" -v
```

Expected: `FAILED` — 404

- [ ] **Step 3: Add endpoint to `web_app.py`** (after `set_provider`)

```python
@app.get("/api/report/pl")
def report_pl(from_date: str = "", to_date: str = "") -> dict[str, Any]:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected for this business.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][: len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [r for r in data_rows if (not from_date or str(r[0]).strip() >= from_date) and (not to_date or str(r[0]).strip() <= to_date)]
        income_by_cat: dict[str, float] = {}
        expense_by_cat: dict[str, float] = {}
        for row in data_rows:
            if len(row) < 5:
                continue
            amount = agent._safe_float(row[3] if len(row) > 3 else 0)
            category = str(row[2]).strip() if len(row) > 2 else "Uncategorized"
            if str(row[4]).strip().lower() == "income":
                income_by_cat[category] = income_by_cat.get(category, 0.0) + amount
            else:
                expense_by_cat[category] = expense_by_cat.get(category, 0.0) + amount
        income_total = sum(income_by_cat.values())
        expense_total = sum(expense_by_cat.values())
        return {
            "business": profile["business_name"],
            "from_date": from_date or None,
            "to_date": to_date or None,
            "income_by_category": [{"category": k, "total": round(v, 2)} for k, v in sorted(income_by_cat.items())],
            "expense_by_category": [{"category": k, "total": round(v, 2)} for k, v in sorted(expense_by_cat.items())],
            "income_total": round(income_total, 2),
            "expense_total": round(expense_total, 2),
            "net": round(income_total - expense_total, 2),
        }
```

- [ ] **Step 4: Run P&L tests**

```bash
pytest tests/test_web_app.py -k "pl_report" -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add web_app.py
git commit -m "feat: add GET /api/report/pl endpoint with optional date range filter"
```

---

## Task 11: Add GET /api/export/csv and GET /api/ledger Endpoints

**Files:**
- Modify: `web_app.py`

- [ ] **Step 1: Add tests to `tests/test_web_app.py`**

Append:
```python
def test_export_csv_returns_csv_file(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Sale", "Consulting", "500.00", "Income", "", ""],
    ]
    with patch("web_app.agent.sheets.read_range", return_value=rows):
        with patch("web_app.agent.memory.get_current_business", return_value={"business_name": "Biz A", "google_sheet_id": "sheet-id"}):
            with patch("web_app.agent.memory.current_business_key", "biz_a"):
                response = client.get("/api/export/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert "Sale" in response.text


def test_ledger_returns_paginated_rows(client):
    rows = [["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]]
    for i in range(25):
        rows.append([f"2026-01-{(i % 28) + 1:02d}", f"Item {i}", "Office", "10.00", "Expense", "", ""])
    with patch("web_app.agent.sheets.read_range", return_value=rows):
        with patch("web_app.agent.memory.get_current_business", return_value={"business_name": "Biz A", "google_sheet_id": "sheet-id"}):
            response = client.get("/api/ledger?page=1&page_size=20")
    data = response.json()
    assert data["total_count"] == 25
    assert len(data["rows"]) == 20
    assert data["total_pages"] == 2


def test_ledger_search_filter(client):
    rows = [
        ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        ["2026-01-10", "Coffee shop", "Meals", "15.00", "Expense", "", ""],
        ["2026-01-11", "Office supplies", "Office", "50.00", "Expense", "", ""],
    ]
    with patch("web_app.agent.sheets.read_range", return_value=rows):
        with patch("web_app.agent.memory.get_current_business", return_value={"business_name": "Biz A", "google_sheet_id": "sheet-id"}):
            response = client.get("/api/ledger?search=coffee")
    data = response.json()
    assert data["total_count"] == 1
    assert data["rows"][0][1] == "Coffee shop"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web_app.py -k "csv or ledger" -v
```

Expected: `3 FAILED`

- [ ] **Step 3: Add imports and two endpoints to `web_app.py`**

Add at the top of `web_app.py` (after existing imports):
```python
import csv
import io
import time
```

After `report_pl`, add:
```python
@app.get("/api/export/csv")
def export_csv(from_date: str = "", to_date: str = "") -> Any:
    from fastapi.responses import StreamingResponse
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][: len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [r for r in data_rows if (not from_date or str(r[0]).strip() >= from_date) and (not to_date or str(r[0]).strip() <= to_date)]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(agent.LEDGER_HEADERS)
        for row in data_rows:
            writer.writerow(agent._normalize_row(row))
        output.seek(0)
        today = time.strftime("%Y-%m-%d")
        filename = f"{agent.memory.current_business_key}-ledger-{today}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/api/ledger")
def get_ledger(page: int = 1, page_size: int = 20, search: str = "", from_date: str = "", to_date: str = "") -> dict[str, Any]:
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            return {"rows": [], "total_count": 0, "page": page, "page_size": page_size, "total_pages": 0}
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][: len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        filtered = []
        for row in data_rows:
            if len(row) < 2:
                continue
            date_str = str(row[0]).strip()
            if from_date and date_str < from_date:
                continue
            if to_date and date_str > to_date:
                continue
            if search:
                desc = str(row[1]).lower() if len(row) > 1 else ""
                cat = str(row[2]).lower() if len(row) > 2 else ""
                if search.lower() not in desc and search.lower() not in cat:
                    continue
            filtered.append(agent._normalize_row(row))
        total_count = len(filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return {"rows": filtered[start: start + page_size], "total_count": total_count, "page": page, "page_size": page_size, "total_pages": total_pages}
```

- [ ] **Step 4: Run all new endpoint tests**

```bash
pytest tests/test_web_app.py -k "csv or ledger" -v
```

Expected: `3 passed`

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add web_app.py
git commit -m "feat: add GET /api/export/csv and GET /api/ledger with pagination and filters"
```

---

## Tasks 12-14: UI Rewrite (index.html, styles.css, app.js)

These three tasks are full file rewrites. The complete file contents are large and contain HTML rendering logic. Write them sequentially.

### Task 12: ui/index.html

The file implements the tabbed layout described in the design spec. Structure:

```
<body>
  #toast-container            — fixed toast host
  #settings-backdrop          — click-to-close overlay
  <aside #settings-panel>     — slide-over with provider/mode selectors + workspace links
  <div.app-shell>
    <header.top-bar>          — logo | business select | model badge | settings gear
    <nav.tab-bar>             — 5 tab buttons: Dashboard Ledger Reports Documents Chat
    <main.tab-content>
      #tab-dashboard          — 5 metric cards + recent-transactions + recent-audits
      #tab-ledger             — filter bar + inline transaction form (collapsible) + paginated table
      #tab-reports            — date pickers + generate button + export CSV + P&L tables + net row
      #tab-documents          — upload form + #document-drafts container
      #tab-chat               — voice controls + #chat-log + composer form
```

- [ ] **Step 1: Write `ui/index.html`**

Write the complete HTML following the structure above. All element IDs must match exactly as listed in the structure (they are referenced by `app.js`). Key IDs referenced by JS:

`toast-container, settings-backdrop, settings-panel, settings-open, settings-close, provider-select, apply-provider, model-mode-select, apply-mode, model-status, workspace-status, sheet-link, doc-link, learned-count, model-badge, boot-warning, business-select, tab-dashboard, tab-ledger, tab-reports, tab-documents, tab-chat, metric-transactions, metric-income, metric-expenses, metric-net, metric-flagged, recent-transactions, recent-audits, ledger-search, ledger-from, ledger-to, ledger-filter-btn, post-transaction-btn, transaction-form-panel, transaction-form, cancel-transaction, tx-date, tx-type, tx-description, tx-category, tx-amount, tx-reference, tx-notes, ledger-body, ledger-page-info, ledger-prev, ledger-next, report-from, report-to, generate-report-btn, export-csv-btn, report-output, income-body, expense-body, income-total-cell, expense-total-cell, net-profit-row, net-profit-value, document-form, document-file, document-note, document-drafts, voice-button, voice-status, speak-toggle, chat-log, chat-form, message-input`

- [ ] **Step 2: Verify the page loads**

```bash
source .venv/bin/activate && export MODEL_PROVIDER=ollama
python web_app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
kill %1
```

Expected: `200`

- [ ] **Step 3: Commit**

```bash
git add ui/index.html
git commit -m "feat: rewrite index.html with tabbed layout and top bar"
```

---

### Task 13: ui/styles.css

Full rewrite with the design tokens from the spec. All CSS rules needed:

Design tokens (`:root`): `--bg #F8FAFC`, `--panel #FFFFFF`, `--border #E2E8F0`, `--text #0F172A`, `--muted #64748B`, `--accent #2563EB`, `--accent-hover #1D4ED8`, `--accent-subtle #EFF6FF`, `--success #16A34A`, `--success-bg #F0FDF4`, `--danger #DC2626`, `--danger-bg #FEF2F2`, `--shadow-sm`, `--shadow-md`, `--radius 12px`, `--radius-sm 8px`, `--font Inter system-ui`, `--top-bar-h 60px`, `--tab-bar-h 48px`.

Component rules needed: `.top-bar`, `.tab-bar`, `.tab-btn` (with `.active` state), `.app-shell`, `.tab-content`, `.tab-pane` (hidden/active), `.panel`, `.panel-title`, `.panel-grid`, `.metric-grid`, `.metric-card`, `.metric-value` (`.positive`/`.negative`), form elements (`input`, `select`, `textarea`), `.primary-button`, `.secondary-button` (`.active`), `.data-table`, `.ledger-toolbar`, `.filter-group`, `.pagination`, `.report-toolbar`, `.report-grid`, `.net-profit-row` (`.positive`/`.negative`), `.chat-log`, `.message` (`.user`/`.agent`), `.composer`, `.presentation-block` and sub-elements, `.item-list`, `.list-item`, `#toast-container`, `.toast` (`.success`/`.error`/`.info`) with `toast-in`/`toast-out` keyframes, `.skeleton` with shimmer keyframe, `.settings-backdrop`, `.settings-panel`, `.hidden`, responsive breakpoints at 900px and 600px.

- [ ] **Step 1: Write `ui/styles.css`**

Write the complete stylesheet following all component rules above.

- [ ] **Step 2: Verify the stylesheet is served**

```bash
source .venv/bin/activate && python web_app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/ui/styles.css
kill %1
```

Expected: `200`

- [ ] **Step 3: Commit**

```bash
git add ui/styles.css
git commit -m "feat: rewrite styles.css with clean modern light design system"
```

---

### Task 14: ui/app.js

Full rewrite. The file must implement these capabilities in order:

1. **`esc(v)`** — HTML entity sanitizer (replaces `&`, `<`, `>`, `"` — MUST be applied to ALL user data before any DOM insertion)
2. **`fmt(v)`** — USD formatter via `Intl.NumberFormat`
3. **Toast system** — `showToast(message, type)` creates a `.toast.{type}` div, appends to `#toast-container`, auto-removes after 4000ms with `toast-out` animation
4. **Tab routing** — click handler on `.tab-btn` toggles `.active` on buttons and `.active` on `.tab-pane` elements; switches to `tab-${btn.dataset.tab}`; fetches ledger when Ledger tab is activated
5. **Settings panel** — open/close via `#settings-open`, `#settings-close`, backdrop click, and `Escape` key
6. **`updateStatus(status, latestPresentation)`** — populates business select, model badge, boot warning, settings status, workspace links, metric cards (removes `.skeleton`), calls `renderRecentTransactions`, `renderRecentAudits`, `renderConversation`
7. **`renderRecentTransactions(items, ledgerError)`** — renders `.list-item` cards in `#recent-transactions`
8. **`renderRecentAudits(items)`** — renders `.list-item` cards in `#recent-audits`
9. **`renderConversation(conversation, latestPresentation)`** — clears `#chat-log`, renders user + agent messages
10. **`appendMessage(role, text, presentation)`** — appends a `.message.{role}` to `#chat-log`
11. **`renderPresentation(p)`** — returns HTML string for presentation blocks (stats, table, sources, approval button, document preview) — ALL values must be passed through `esc()`
12. **Provider switch** — `#apply-provider` POSTs to `/api/provider`, calls `updateStatus`, shows toast
13. **Mode switch** — `#apply-mode` POSTs to `/api/model-mode`, calls `updateStatus`, shows toast
14. **Business auto-switch** — `#business-select` `change` event POSTs to `/api/switch-business`
15. **`fetchLedger(page)`** — GETs `/api/ledger` with search/from/to/page params, renders `#ledger-body` rows, updates pagination controls
16. **Transaction form toggle** — `#post-transaction-btn` toggles `#transaction-form-panel` hidden class
17. **Transaction submit** — `#transaction-form` submit POSTs to `/api/record-transaction`, shows toast, resets form, calls `fetchLedger(1)`
18. **P&L report** — `#generate-report-btn` GETs `/api/report/pl`, renders income/expense tables, net profit row with color class
19. **CSV export** — `#export-csv-btn` sets `window.location.href` to `/api/export/csv` with date params
20. **Document upload** — `#document-form` submit POSTs multipart to `/api/upload-document`, appends draft card to `#document-drafts`
21. **Draft approval** — delegated click on `.approval-button` in `#document-drafts` POSTs to `/api/approve-document-draft`
22. **Chat submit** — `#chat-form` submit POSTs to `/api/message`, calls `appendMessage` for both sides
23. **Cmd+Enter shortcut** — `keydown` on `#message-input`, submits form when `e.metaKey || e.ctrlKey`
24. **Voice recognition** — `configureVoice()` sets up `SpeechRecognition` on `#voice-button`, transcribes to `#message-input`
25. **Voice reply toggle** — `#speak-toggle` toggles `speakReplies` flag, calls `speechSynthesis.speak` after agent responses
26. **Init** — `configureVoice()` then `fetchStatus()` (GETs `/api/status`, calls `updateStatus`)

- [ ] **Step 1: Write `ui/app.js`**

Write the complete JavaScript implementing all 26 capabilities above.

- [ ] **Step 2: Smoke test in browser**

```bash
source .venv/bin/activate && export MODEL_PROVIDER=ollama
python web_app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/ui/app.js
kill %1
```

Expected: `200`

Open `http://127.0.0.1:8000` in a browser. Verify:
- 5 tabs are visible and clickable
- Dashboard tab shows 5 metric cards (skeleton animates then resolves)
- Settings gear opens slide-over
- Business dropdown shows available businesses

- [ ] **Step 3: Commit**

```bash
git add ui/app.js
git commit -m "feat: rewrite app.js with tab router, toast, P&L, CSV export, settings panel"
```

---

## Task 15: Final Verification

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/muhammadnazam/Documents/CPA-Agent
source .venv/bin/activate
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Verify server starts and key endpoints respond**

```bash
export MODEL_PROVIDER=ollama
python web_app.py &
sleep 3
curl -s http://127.0.0.1:8000/api/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('status ok' if 'dashboard' in d else 'FAIL')"
curl -s "http://127.0.0.1:8000/api/ledger?page=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ledger ok' if 'total_count' in d else 'FAIL')"
curl -s "http://127.0.0.1:8000/api/report/pl" | python3 -c "import sys,json; d=json.load(sys.stdin); print('pl ok' if 'net' in d or 'detail' in d else 'FAIL')"
kill %1
```

Expected: `status ok`, `ledger ok`, `pl ok`

- [ ] **Step 3: Verify OpenRouter routing**

```bash
source .venv/bin/activate
export MODEL_PROVIDER=openrouter OPENROUTER_API_KEY=test-key
python -c "from core.model_client import get_model_client; print(type(get_model_client(purpose='reasoning', reasoning_mode='fast')).__name__)"
```

Expected: `OpenRouterClient`

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: final verification pass — all acceptance criteria confirmed"
```

---

## Spec Coverage Map

| Spec Requirement | Task |
|---|---|
| OpenRouter client with `https://openrouter.ai/api/v1` | Task 2 |
| `OPENROUTER_MODEL` env var respected | Task 2 |
| `model_client.py` openrouter branch | Task 3 |
| Fix brittle date inference (no hardcoded keywords) | Task 4 |
| Fix ledger row limit A1:G50 -> A1:G | Task 5 |
| Wire `calculate_payroll` action | Task 6 |
| Wire `research_tax` action | Task 7 |
| `pending_document_drafts` TTL eviction + cap | Task 8 |
| `POST /api/provider` runtime provider switching | Task 9 |
| `GET /api/report/pl` with date range | Task 10 |
| `GET /api/export/csv` streaming download | Task 11 |
| `GET /api/ledger` pagination + search + date filter | Task 11 |
| UI tabbed layout (top bar + 5 tabs) | Task 12 |
| Clean modern light CSS design system | Task 13 |
| Net Profit metric card with +/- color coding | Task 14 |
| Toast notifications | Task 14 |
| Cmd+Enter chat shortcut | Task 14 |
| Provider selector in settings slide-over | Task 14 |
| Skeleton loading states on metric cards | Task 14 |
