# Phase 1 — Smart Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver sidebar navigation, AI hybrid categorization, and recurring transactions — all wired into the existing agent and 5-second status poll.

**Architecture:** Seven sequential tasks. Tasks 1–2 are pure infrastructure (nav + memory). Tasks 3–5 are the categorization feature (engine → API → UI). Tasks 6–8 are the recurring feature (engine → API → UI + chat). Each task is independently testable and committable.

**Tech Stack:** Vanilla JS + CSS (sidebar), Python/FastAPI (API), JSON files under `memory/long_term/{business_key}/` (persistence), existing `GoogleSheetsManager.read_range` (ledger reads), existing `CPAAgent.record_structured_transaction` (ledger writes).

**Spec:** `docs/superpowers/specs/2026-04-27-cpa-agent-features-design.md`

---

## Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `ui/index.html` | Modify | Replace top tab bar with sidebar |
| `ui/styles.css` | Modify | Sidebar layout, progress badge, category badge styles |
| `ui/app.js` | Modify | Sidebar routing, categorization UI, recurring UI |
| `memory_manager.py` | Modify | Add load/save for category_rules + recurring |
| `skills/categorization_engine.py` | Create | suggest_category, save_rule, backfill |
| `skills/recurring_engine.py` | Create | CRUD schedules, run_due_schedules |
| `web_app.py` | Modify | 6 new endpoints (category + recurring) |
| `main.py` | Modify | Wire both engines into agent + chat + status poll |
| `tests/test_categorization_engine.py` | Create | Unit tests for categorization engine |
| `tests/test_recurring_engine.py` | Create | Unit tests for recurring engine |

---

## Task 1: Sidebar Navigation

**Files:**
- Modify: `ui/index.html`
- Modify: `ui/styles.css`
- Modify: `ui/app.js`

**Context:** The current page uses a `.tab-btn[data-tab=X]` pattern with `.tab-content` divs. The sidebar keeps the same `data-tab` convention so all existing tab controllers (initLedger, initChat, etc.) continue to work unchanged. The only change is the visual structure: tabs move from a horizontal row at the top to a vertical list on the left.

- [ ] **Step 1: Add sidebar HTML to `ui/index.html`**

  Remove the existing `<div class="tabs">...</div>` block and replace the entire page layout with a two-column flex structure. Find the opening `<body>` tag and restructure:

  ```html
  <body>
    <!-- Top bar (model badge + settings only) -->
    <header class="top-bar">
      <span class="brand">CPA-Agent</span>
      <div class="top-bar-right">
        <span id="boot-warning" class="boot-warning hidden">⚠ Connection issue</span>
        <span id="model-badge" class="model-badge">—</span>
        <button id="settings-open" class="icon-btn" aria-label="Settings">⚙</button>
      </div>
    </header>

    <!-- App shell -->
    <div class="app-shell">

      <!-- Sidebar -->
      <nav class="sidebar">
        <div class="sidebar-business">
          <div class="sidebar-biz-icon">N</div>
          <select id="business-select" class="sidebar-biz-select"></select>
        </div>

        <a class="sidebar-item" data-tab="dashboard">⬛ Dashboard</a>

        <div class="sidebar-group-label">Books</div>
        <a class="sidebar-item" data-tab="ledger">📒 Ledger</a>
        <a class="sidebar-item" data-tab="recurring">🔁 Recurring</a>

        <div class="sidebar-group-label">Reports</div>
        <a class="sidebar-item" data-tab="reports">📈 P&amp;L</a>

        <div class="sidebar-group-label">Tools</div>
        <a class="sidebar-item" data-tab="documents">📄 Documents</a>
        <a class="sidebar-item" data-tab="chat">💬 Chat</a>
      </nav>

      <!-- Main content -->
      <main class="main-content">
        <!-- Dashboard tab -->
        <section id="tab-dashboard" class="tab-content">
          <!-- existing dashboard content moved here -->
        </section>

        <!-- Ledger tab -->
        <section id="tab-ledger" class="tab-content hidden">
          <!-- existing ledger content moved here -->
        </section>

        <!-- Recurring tab (new) -->
        <section id="tab-recurring" class="tab-content hidden">
          <h2>Recurring Transactions</h2>
          <p class="section-hint">Create via Chat: <em>"Schedule rent $2000 expense on the 1st every month"</em></p>
          <table class="data-table" id="recurring-table">
            <thead>
              <tr><th>Description</th><th>Amount</th><th>Category</th><th>Frequency</th><th>Next Date</th><th>Actions</th></tr>
            </thead>
            <tbody id="recurring-body"></tbody>
          </table>
        </section>

        <!-- Reports tab -->
        <section id="tab-reports" class="tab-content hidden">
          <!-- existing reports content moved here -->
        </section>

        <!-- Documents tab -->
        <section id="tab-documents" class="tab-content hidden">
          <!-- existing documents content moved here -->
        </section>

        <!-- Chat tab -->
        <section id="tab-chat" class="tab-content hidden">
          <!-- existing chat content moved here -->
        </section>
      </main>

    </div>

    <!-- Settings panel (unchanged) -->
    <!-- ... existing settings panel markup ... -->
  </body>
  ```

  > Note: Move all existing section content into the correct `<section id="tab-X">` wrappers. Do not delete any existing IDs or elements — only restructure their parent containers.

- [ ] **Step 2: Add sidebar CSS to `ui/styles.css`**

  Append to the end of `styles.css`:

  ```css
  /* ── App shell ─────────────────────────────────────────── */
  .app-shell {
    display: flex;
    height: calc(100vh - 52px); /* minus top-bar height */
    overflow: hidden;
  }

  /* ── Sidebar ──────────────────────────────────────────── */
  .sidebar {
    width: 200px;
    flex-shrink: 0;
    background: #1e293b;
    color: #cbd5e1;
    overflow-y: auto;
    padding: 0.75rem 0;
    display: flex;
    flex-direction: column;
  }

  .sidebar-business {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem 0.75rem;
    border-bottom: 1px solid #334155;
    margin-bottom: 0.5rem;
  }

  .sidebar-biz-icon {
    width: 28px;
    height: 28px;
    background: #3b82f6;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 700;
    font-size: 0.8rem;
    flex-shrink: 0;
  }

  .sidebar-biz-select {
    background: transparent;
    border: none;
    color: #f1f5f9;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
    outline: none;
  }

  .sidebar-biz-select option { background: #1e293b; }

  .sidebar-group-label {
    padding: 0.6rem 0.75rem 0.2rem;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #64748b;
    font-weight: 600;
  }

  .sidebar-item {
    display: block;
    padding: 0.35rem 0.75rem;
    color: #cbd5e1;
    text-decoration: none;
    font-size: 0.82rem;
    border-radius: 0 6px 6px 0;
    margin-right: 0.5rem;
    cursor: pointer;
    transition: background 0.1s;
  }

  .sidebar-item:hover { background: #334155; }
  .sidebar-item.active { background: #3b82f6; color: #fff; }

  /* ── Main content ─────────────────────────────────────── */
  .main-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
    background: #f8fafc;
  }

  /* ── Category badge ───────────────────────────────────── */
  .cat-badge-ai {
    display: inline-block;
    background: #dcfce7;
    color: #16a34a;
    padding: 0.1rem 0.45rem;
    border-radius: 99px;
    font-size: 0.72rem;
    cursor: pointer;
  }

  .cat-badge-ai::before { content: "✦ "; }

  .cat-badge-uncategorized {
    display: inline-block;
    background: #fef9c3;
    color: #a16207;
    padding: 0.1rem 0.45rem;
    border-radius: 99px;
    font-size: 0.72rem;
    cursor: pointer;
  }

  .section-hint {
    font-size: 0.82rem;
    color: #6b7280;
    margin-bottom: 1rem;
  }
  ```

- [ ] **Step 3: Update sidebar routing in `ui/app.js`**

  Replace `initTabs()` with a sidebar-aware version. Find the existing `initTabs` function and replace it entirely:

  ```javascript
  function initTabs() {
    var items = document.querySelectorAll('.sidebar-item');
    items.forEach(function (item) {
      item.addEventListener('click', function () {
        var tab = item.dataset.tab;
        // Deactivate all
        items.forEach(function (i) { i.classList.remove('active'); });
        document.querySelectorAll('.tab-content').forEach(function (s) {
          s.classList.add('hidden');
        });
        // Activate selected
        item.classList.add('active');
        var section = document.getElementById('tab-' + tab);
        if (section) { section.classList.remove('hidden'); }
        if (tab === 'ledger') { fetchLedger(1); }
        if (tab === 'recurring') { fetchRecurring(); }
      });
    });
    // Activate dashboard by default
    var first = document.querySelector('.sidebar-item[data-tab="dashboard"]');
    if (first) { first.click(); }
  }
  ```

- [ ] **Step 4: Verify in browser**

  Run `source .venv/bin/activate && uvicorn web_app:app --reload` and open `http://localhost:8000`.

  Confirm: sidebar visible on left, all existing tabs reachable, dashboard active by default, ledger loads when Ledger is clicked.

- [ ] **Step 5: Commit**

  ```bash
  git add ui/index.html ui/styles.css ui/app.js
  git commit -m "feat: replace top tabs with sidebar navigation"
  ```

---

## Task 2: MemoryManager Extensions

**Files:**
- Modify: `memory_manager.py`

**Context:** Two new JSON files per business: `category_rules.json` and `recurring.json`. Each needs an `_ensure_file`, `load_*`, and `save_*` method. The pattern matches existing methods like `load_learned_sources` / `record_learned_source`.

- [ ] **Step 1: Write failing tests**

  Create `tests/test_memory_extensions.py`:

  ```python
  import json, pytest
  from pathlib import Path
  from memory_manager import MemoryManager

  @pytest.fixture
  def mgr(tmp_path):
      # Create a minimal business profile so MemoryManager can boot
      biz_dir = tmp_path / "long_term" / "test_biz"
      biz_dir.mkdir(parents=True)
      (biz_dir / "config.json").write_text(json.dumps({
          "business_name": "Test Biz",
          "google_sheet_id": "x", "google_doc_id": "x",
          "local_memory_db": "", "federal_ein": "", "state": "", "default_books_currency": "USD"
      }))
      (tmp_path / "active_business.json").write_text(json.dumps({"active_business": "test_biz"}))
      return MemoryManager(tmp_path)

  def test_load_category_rules_returns_empty_on_new_business(mgr):
      data = mgr.load_category_rules()
      assert data == {"rules": []}

  def test_save_and_reload_category_rules(mgr):
      mgr.save_category_rules({"rules": [{"id": "1", "pattern": "aws", "category": "Cloud"}]})
      data = mgr.load_category_rules()
      assert data["rules"][0]["category"] == "Cloud"

  def test_load_recurring_returns_empty_on_new_business(mgr):
      data = mgr.load_recurring()
      assert data == {"schedules": []}

  def test_save_and_reload_recurring(mgr):
      mgr.save_recurring({"schedules": [{"id": "1", "description": "Rent", "amount": 2000}]})
      data = mgr.load_recurring()
      assert data["schedules"][0]["description"] == "Rent"
  ```

- [ ] **Step 2: Run to confirm failure**

  ```bash
  source .venv/bin/activate && pytest tests/test_memory_extensions.py -v
  ```

  Expected: FAIL — `AttributeError: 'MemoryManager' object has no attribute 'load_category_rules'`

- [ ] **Step 3: Add the four methods to `memory_manager.py`**

  After `load_learned_sources` (around line 237), add:

  ```python
  def _category_rules_path(self) -> Path:
      return self.long_term_dir / self.current_business_key / "category_rules.json"

  def load_category_rules(self) -> dict:
      path = self._category_rules_path()
      if not path.exists():
          return {"rules": []}
      with path.open("r", encoding="utf-8") as f:
          return json.load(f)

  def save_category_rules(self, data: dict) -> None:
      path = self._category_rules_path()
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(json.dumps(data, indent=2), encoding="utf-8")

  def _recurring_path(self) -> Path:
      return self.long_term_dir / self.current_business_key / "recurring.json"

  def load_recurring(self) -> dict:
      path = self._recurring_path()
      if not path.exists():
          return {"schedules": []}
      with path.open("r", encoding="utf-8") as f:
          return json.load(f)

  def save_recurring(self, data: dict) -> None:
      path = self._recurring_path()
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(json.dumps(data, indent=2), encoding="utf-8")
  ```

- [ ] **Step 4: Run tests to confirm pass**

  ```bash
  pytest tests/test_memory_extensions.py -v
  ```

  Expected: 4 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add memory_manager.py tests/test_memory_extensions.py
  git commit -m "feat: add category_rules and recurring load/save to MemoryManager"
  ```

---

## Task 3: Categorization Engine

**Files:**
- Create: `skills/categorization_engine.py`
- Create: `tests/test_categorization_engine.py`

**Context:** Three methods. `suggest_category` does a case-insensitive substring match against stored rules, returning the highest-confidence match. `save_rule` normalises the description to lowercase, upserts the rule (updates if same pattern+category already exists). `backfill_rules_from_ledger` finds vendor+category pairs that appear ≥2 times and creates rules from them.

- [ ] **Step 1: Write failing tests**

  Create `tests/test_categorization_engine.py`:

  ```python
  import pytest
  from skills.categorization_engine import CategorizationEngine

  RULES = {
      "rules": [
          {"id": "r1", "pattern": "starbucks", "match_type": "contains",
           "category": "Meals & Entertainment", "confidence": 0.95, "use_count": 10},
          {"id": "r2", "pattern": "aws", "match_type": "contains",
           "category": "Cloud Infra", "confidence": 0.9, "use_count": 5},
      ]
  }

  def test_suggest_returns_match_for_known_vendor():
      engine = CategorizationEngine(rules_data=RULES)
      result = engine.suggest_category("Starbucks #4421")
      assert result is not None
      assert result["category"] == "Meals & Entertainment"
      assert result["confidence"] == 0.95

  def test_suggest_returns_none_for_unknown_vendor():
      engine = CategorizationEngine(rules_data=RULES)
      assert engine.suggest_category("Random New Vendor XYZ") is None

  def test_suggest_is_case_insensitive():
      engine = CategorizationEngine(rules_data=RULES)
      result = engine.suggest_category("AMAZON WEB SERVICES AWS")
      assert result is not None
      assert result["category"] == "Cloud Infra"

  def test_save_rule_adds_new_rule():
      engine = CategorizationEngine(rules_data={"rules": []})
      engine.save_rule("Office Depot", "Office Supplies")
      result = engine.suggest_category("Office Depot purchase")
      assert result is not None
      assert result["category"] == "Office Supplies"

  def test_save_rule_updates_existing_rule():
      engine = CategorizationEngine(rules_data=RULES)
      engine.save_rule("starbucks", "Coffee")  # override
      result = engine.suggest_category("Starbucks #111")
      assert result["category"] == "Coffee"

  def test_backfill_creates_rules_for_repeated_pairs():
      engine = CategorizationEngine(rules_data={"rules": []})
      rows = [
          ["2026-01-01", "Starbucks", "Meals", "10", "Expense", "", ""],
          ["2026-01-02", "Starbucks", "Meals", "8",  "Expense", "", ""],
          ["2026-01-03", "AWS",       "Cloud", "89", "Expense", "", ""],
          ["2026-01-04", "AWS",       "Cloud", "89", "Expense", "", ""],
          ["2026-01-05", "OneTime",   "Misc",  "50", "Expense", "", ""],
      ]
      count = engine.backfill_rules_from_ledger(rows)
      assert count == 2  # Starbucks+AWS had ≥2 occurrences; OneTime did not
      assert engine.suggest_category("Starbucks latte") is not None
      assert engine.suggest_category("AWS bill") is not None
      assert engine.suggest_category("OneTime payment") is None
  ```

- [ ] **Step 2: Run to confirm failure**

  ```bash
  pytest tests/test_categorization_engine.py -v
  ```

  Expected: FAIL — `ModuleNotFoundError: No module named 'skills.categorization_engine'`

- [ ] **Step 3: Implement `skills/categorization_engine.py`**

  Create the file:

  ```python
  from __future__ import annotations

  import uuid
  from collections import Counter
  from typing import Any


  class CategorizationEngine:
      def __init__(self, rules_data: dict[str, Any] | None = None) -> None:
          self._rules: list[dict[str, Any]] = (rules_data or {}).get("rules", [])

      def get_rules_data(self) -> dict[str, Any]:
          return {"rules": self._rules}

      def suggest_category(self, description: str) -> dict[str, Any] | None:
          desc_lower = description.lower()
          best: dict[str, Any] | None = None
          for rule in self._rules:
              if rule["pattern"] in desc_lower:
                  if best is None or rule.get("confidence", 0) > best.get("confidence", 0):
                      best = rule
          if best is None:
              return None
          return {
              "category": best["category"],
              "confidence": best.get("confidence", 0.8),
              "rule_id": best["id"],
          }

      def save_rule(self, description: str, category: str) -> dict[str, Any]:
          pattern = description.strip().lower()
          for rule in self._rules:
              if rule["pattern"] == pattern:
                  rule["category"] = category
                  rule["confidence"] = min(rule.get("confidence", 0.8) + 0.05, 1.0)
                  rule["use_count"] = rule.get("use_count", 0) + 1
                  return rule
          new_rule: dict[str, Any] = {
              "id": str(uuid.uuid4()),
              "pattern": pattern,
              "match_type": "contains",
              "category": category,
              "confidence": 0.8,
              "use_count": 1,
          }
          self._rules.append(new_rule)
          return new_rule

      def backfill_rules_from_ledger(self, rows: list[list[Any]]) -> int:
          pairs: Counter = Counter()
          for row in rows:
              if len(row) < 3:
                  continue
              vendor = str(row[1]).strip().lower()
              category = str(row[2]).strip()
              if vendor and category:
                  pairs[(vendor, category)] += 1
          created = 0
          for (vendor, category), count in pairs.items():
              if count >= 2:
                  existing = next((r for r in self._rules if r["pattern"] == vendor), None)
                  if not existing:
                      self._rules.append({
                          "id": str(uuid.uuid4()),
                          "pattern": vendor,
                          "match_type": "contains",
                          "category": category,
                          "confidence": 0.85,
                          "use_count": count,
                      })
                      created += 1
          return created
  ```

- [ ] **Step 4: Run tests to confirm pass**

  ```bash
  pytest tests/test_categorization_engine.py -v
  ```

  Expected: 6 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add skills/categorization_engine.py tests/test_categorization_engine.py
  git commit -m "feat: add CategorizationEngine with suggest, save_rule, and backfill"
  ```

---

## Task 4: Categorization API Endpoints

**Files:**
- Modify: `web_app.py`
- Modify: `main.py`

**Context:** Two endpoints. `GET /api/category/suggest` is stateless — it instantiates the engine from disk on each call. `POST /api/category-rule` saves a new or updated rule and persists it.

- [ ] **Step 1: Add engine instantiation helper to `main.py`**

  In `main.py`, import and instantiate `CategorizationEngine` in `CPAAgent.__init__`. After `self.knowledge = KnowledgeManager()`, add:

  ```python
  from skills.categorization_engine import CategorizationEngine

  # In __init__:
  self.categorization = CategorizationEngine(
      rules_data=self.memory.load_category_rules()
  )
  ```

  Add a method to persist rules back to disk after any change:

  ```python
  def _save_category_rules(self) -> None:
      self.memory.save_category_rules(self.categorization.get_rules_data())
  ```

- [ ] **Step 2: Add two endpoints to `web_app.py`**

  After the `/api/provider` endpoint, add:

  ```python
  class CategoryRuleRequest(BaseModel):
      description: str
      category: str

  @app.get("/api/category/suggest")
  def suggest_category(description: str = "") -> dict:
      if not description:
          raise HTTPException(status_code=400, detail="description is required")
      with agent_lock:
          result = agent.categorization.suggest_category(description)
          return result if result else {"category": None, "confidence": 0.0, "rule_id": None}

  @app.post("/api/category-rule")
  def save_category_rule(payload: CategoryRuleRequest) -> dict:
      with agent_lock:
          rule = agent.categorization.save_rule(payload.description, payload.category)
          agent._save_category_rules()
          return {"ok": True, "rule": rule}
  ```

- [ ] **Step 3: Wire backfill on agent startup**

  In `CPAAgent.__init__`, after creating `self.categorization`, trigger backfill if no rules exist yet:

  ```python
  if not self.categorization._rules:
      try:
          profile = self.memory.get_current_business()
          if profile.get("google_sheet_id"):
              rows = self.sheets.read_range(
                  spreadsheet_id=profile["google_sheet_id"],
                  range_name="Ledger!A2:G200",
              )
              count = self.categorization.backfill_rules_from_ledger(rows)
              if count:
                  self._save_category_rules()
      except Exception:  # noqa: BLE001
          pass  # backfill is best-effort; don't block startup
  ```

- [ ] **Step 4: Test endpoints manually**

  With the server running:

  ```bash
  curl "http://localhost:8000/api/category/suggest?description=Starbucks+latte"
  # Expected: {"category": "Meals & Entertainment", "confidence": ..., "rule_id": ...}
  # (or null if no rules exist yet — will populate after first transaction correction)

  curl -X POST http://localhost:8000/api/category-rule \
    -H "Content-Type: application/json" \
    -d '{"description": "Starbucks", "category": "Meals & Entertainment"}'
  # Expected: {"ok": true, "rule": {...}}
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add web_app.py main.py
  git commit -m "feat: add category suggest and save-rule API endpoints"
  ```

---

## Task 5: Categorization UI in Ledger

**Files:**
- Modify: `ui/app.js`

**Context:** When the ledger table renders a row, the category cell should show a ✦ green badge if the AI knows the vendor, or a yellow "?" badge if uncategorised. Clicking either badge fetches a suggestion and opens an inline `<select>` with common categories + the suggestion pre-selected. On change, it calls `POST /api/category-rule` silently.

Common categories list (hardcoded in JS): `["Meals & Entertainment", "Cloud Infra", "Office Supplies", "Rent", "Utilities", "Marketing", "Travel", "Payroll", "Professional Services", "Software", "Equipment", "Misc"]`

- [ ] **Step 1: Add `renderCategoryCell` helper to `ui/app.js`**

  Before the `fetchLedger` function, add:

  ```javascript
  var COMMON_CATEGORIES = [
    "Meals & Entertainment","Cloud Infra","Office Supplies","Rent",
    "Utilities","Marketing","Travel","Payroll","Professional Services",
    "Software","Equipment","Misc"
  ];

  function renderCategoryCell(td, description, category) {
    td.textContent = '';
    var badge = document.createElement('span');
    var known = category && category.toLowerCase() !== 'uncategorized' && category !== '';
    badge.className = known ? 'cat-badge-ai' : 'cat-badge-uncategorized';
    badge.textContent = known ? category : '? Uncategorized';
    badge.addEventListener('click', function () {
      td.textContent = '';
      var sel = document.createElement('select');
      sel.style.fontSize = '0.78rem';
      var opts = known ? [category] : [];
      COMMON_CATEGORIES.forEach(function (c) {
        if (opts.indexOf(c) === -1) { opts.push(c); }
      });
      opts.forEach(function (c) {
        var o = document.createElement('option');
        o.value = c; o.textContent = c;
        if (c === category) { o.selected = true; }
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () {
        var chosen = sel.value;
        fetch('/api/category-rule', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: description, category: chosen })
        }).catch(function () {});
        renderCategoryCell(td, description, chosen);
      });
      td.appendChild(sel);
      sel.focus();
    });
    td.appendChild(badge);
  }
  ```

- [ ] **Step 2: Call `renderCategoryCell` inside the ledger row renderer**

  Find the function in `app.js` that builds ledger table rows (look for where `ledger-body` cells are created). For the category column `td`, replace plain `td.textContent = row[2]` with:

  ```javascript
  renderCategoryCell(td, row[1] || '', row[2] || '');
  ```

- [ ] **Step 3: Verify in browser**

  Open the Ledger tab. Existing transactions should show their category as a ✦ green badge. Clicking it should open a dropdown. Selecting a new category should silently save the rule.

- [ ] **Step 4: Commit**

  ```bash
  git add ui/app.js
  git commit -m "feat: add AI category badge and inline correction to Ledger"
  ```

---

## Task 6: Recurring Engine

**Files:**
- Create: `skills/recurring_engine.py`
- Create: `tests/test_recurring_engine.py`

**Context:** `run_due_schedules` is called on every status poll. It must be idempotent — if a schedule was already posted today, it must not post again. Use the `last_posted_date` field on each schedule to guard against double-posting.

- [ ] **Step 1: Write failing tests**

  Create `tests/test_recurring_engine.py`:

  ```python
  import pytest
  from datetime import date
  from skills.recurring_engine import RecurringEngine

  def make_engine(schedules=None):
      data = {"schedules": schedules or []}
      return RecurringEngine(recurring_data=data)

  def test_create_schedule_adds_entry():
      engine = make_engine()
      s = engine.create_schedule(
          description="Rent", amount=2000.0, category="Rent",
          entry_type="Expense", frequency="monthly",
          day_of_period=1, start_date="2026-05-01"
      )
      assert s["description"] == "Rent"
      assert s["next_date"] == "2026-05-01"
      assert s["active"] is True

  def test_cancel_schedule_sets_inactive():
      engine = make_engine([{
          "id": "abc", "description": "Rent", "amount": 2000, "category": "Rent",
          "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
          "next_date": "2026-05-01", "active": True, "last_posted_date": None
      }])
      result = engine.cancel_schedule("abc")
      assert result is True
      assert engine.list_schedules()[0]["active"] is False

  def test_run_due_schedules_returns_due_entry(mocker):
      today = "2026-05-01"
      engine = make_engine([{
          "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
          "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
          "next_date": today, "active": True, "last_posted_date": None
      }])
      due = engine.run_due_schedules(today=today)
      assert len(due) == 1
      assert due[0]["description"] == "Rent"

  def test_run_due_schedules_advances_next_date(mocker):
      today = "2026-05-01"
      engine = make_engine([{
          "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
          "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
          "next_date": today, "active": True, "last_posted_date": None
      }])
      engine.run_due_schedules(today=today)
      schedule = engine.list_schedules()[0]
      assert schedule["next_date"] == "2026-06-01"
      assert schedule["last_posted_date"] == today

  def test_run_due_schedules_is_idempotent():
      today = "2026-05-01"
      engine = make_engine([{
          "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
          "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
          "next_date": today, "active": True, "last_posted_date": today
      }])
      due = engine.run_due_schedules(today=today)
      assert len(due) == 0  # already posted today

  def test_run_due_schedules_skips_inactive():
      today = "2026-05-01"
      engine = make_engine([{
          "id": "abc", "description": "Rent", "amount": 2000.0, "category": "Rent",
          "entry_type": "Expense", "frequency": "monthly", "day_of_period": 1,
          "next_date": today, "active": False, "last_posted_date": None
      }])
      due = engine.run_due_schedules(today=today)
      assert len(due) == 0
  ```

- [ ] **Step 2: Run to confirm failure**

  ```bash
  pytest tests/test_recurring_engine.py -v
  ```

  Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `skills/recurring_engine.py`**

  ```python
  from __future__ import annotations

  import uuid
  from datetime import date, timedelta
  from typing import Any


  class RecurringEngine:
      def __init__(self, recurring_data: dict[str, Any] | None = None) -> None:
          self._schedules: list[dict[str, Any]] = (recurring_data or {}).get("schedules", [])

      def get_recurring_data(self) -> dict[str, Any]:
          return {"schedules": self._schedules}

      def list_schedules(self) -> list[dict[str, Any]]:
          return [s for s in self._schedules if s.get("active", True)]

      def create_schedule(
          self,
          description: str,
          amount: float,
          category: str,
          entry_type: str,
          frequency: str,
          day_of_period: int,
          start_date: str,
      ) -> dict[str, Any]:
          schedule: dict[str, Any] = {
              "id": str(uuid.uuid4()),
              "description": description.strip(),
              "amount": round(float(amount), 2),
              "category": category.strip(),
              "entry_type": entry_type.strip().title(),
              "frequency": frequency.strip().lower(),
              "day_of_period": int(day_of_period),
              "next_date": start_date,
              "active": True,
              "last_posted_date": None,
          }
          self._schedules.append(schedule)
          return schedule

      def cancel_schedule(self, schedule_id: str) -> bool:
          for s in self._schedules:
              if s["id"] == schedule_id:
                  s["active"] = False
                  return True
          return False

      def update_schedule(self, schedule_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
          for s in self._schedules:
              if s["id"] == schedule_id:
                  s.update({k: v for k, v in updates.items() if k != "id"})
                  return s
          return None

      def run_due_schedules(self, today: str | None = None) -> list[dict[str, Any]]:
          today_str = today or date.today().isoformat()
          due = []
          for s in self._schedules:
              if not s.get("active", True):
                  continue
              if s.get("last_posted_date") == today_str:
                  continue
              if s.get("next_date") == today_str:
                  due.append(dict(s))
                  s["last_posted_date"] = today_str
                  s["next_date"] = self._advance_date(today_str, s["frequency"], s["day_of_period"])
          return due

      @staticmethod
      def _advance_date(from_date: str, frequency: str, day_of_period: int) -> str:
          d = date.fromisoformat(from_date)
          if frequency == "daily":
              return (d + timedelta(days=1)).isoformat()
          if frequency == "weekly":
              return (d + timedelta(weeks=1)).isoformat()
          if frequency == "monthly":
              month = d.month + 1 if d.month < 12 else 1
              year = d.year if d.month < 12 else d.year + 1
              last_day = (date(year, month % 12 + 1, 1) - timedelta(days=1)).day if month != 12 else 31
              return date(year, month, min(day_of_period, last_day)).isoformat()
          if frequency == "annually":
              return date(d.year + 1, d.month, d.day).isoformat()
          return (d + timedelta(days=30)).isoformat()
  ```

- [ ] **Step 4: Run tests to confirm pass**

  ```bash
  pytest tests/test_recurring_engine.py -v
  ```

  Expected: 6 PASS

- [ ] **Step 5: Commit**

  ```bash
  git add skills/recurring_engine.py tests/test_recurring_engine.py
  git commit -m "feat: add RecurringEngine with CRUD, idempotent auto-posting, date advance"
  ```

---

## Task 7: Recurring API Endpoints + Status Poll Integration

**Files:**
- Modify: `web_app.py`
- Modify: `main.py`

- [ ] **Step 1: Instantiate RecurringEngine in `CPAAgent.__init__`**

  In `main.py`, import and add after `self.categorization`:

  ```python
  from skills.recurring_engine import RecurringEngine

  # In __init__:
  self.recurring = RecurringEngine(
      recurring_data=self.memory.load_recurring()
  )
  ```

  Add save helper:

  ```python
  def _save_recurring(self) -> None:
      self.memory.save_recurring(self.recurring.get_recurring_data())
  ```

- [ ] **Step 2: Hook `run_due_schedules` into `get_status`**

  In `main.py`, find `get_status()`. At the top of the method body, add:

  ```python
  def get_status(self) -> dict[str, Any]:
      # Run any recurring transactions due today
      due = self.recurring.run_due_schedules()
      if due:
          self._save_recurring()
          for entry in due:
              try:
                  self.record_structured_transaction(
                      date=entry["next_date"] or entry.get("last_posted_date", ""),
                      description=entry["description"],
                      category=entry["category"],
                      amount=entry["amount"],
                      entry_type=entry["entry_type"],
                      notes="Auto-posted by recurring schedule",
                  )
              except Exception:  # noqa: BLE001
                  pass
      # ... rest of existing get_status body unchanged
  ```

  > Note: `run_due_schedules` already advanced `next_date` and set `last_posted_date`, so calling it again on the next poll will not re-post. The `entry["next_date"]` at the time of posting is the current due date — use `entry.get("last_posted_date")` for the transaction date since `next_date` has already been advanced by this point. Correct the date field:

  ```python
  self.record_structured_transaction(
      date=entry.get("last_posted_date", ""),
      ...
  )
  ```

- [ ] **Step 3: Add four recurring endpoints to `web_app.py`**

  ```python
  class RecurringCreateRequest(BaseModel):
      description: str
      amount: float
      category: str
      entry_type: str
      frequency: str
      day_of_period: int
      start_date: str

  class RecurringUpdateRequest(BaseModel):
      description: str | None = None
      amount: float | None = None
      category: str | None = None
      frequency: str | None = None
      day_of_period: int | None = None
      next_date: str | None = None

  @app.get("/api/recurring")
  def get_recurring() -> dict:
      with agent_lock:
          return {"schedules": agent.recurring.list_schedules()}

  @app.post("/api/recurring")
  def create_recurring(payload: RecurringCreateRequest) -> dict:
      with agent_lock:
          schedule = agent.recurring.create_schedule(
              description=payload.description, amount=payload.amount,
              category=payload.category, entry_type=payload.entry_type,
              frequency=payload.frequency, day_of_period=payload.day_of_period,
              start_date=payload.start_date,
          )
          agent._save_recurring()
          return {"ok": True, "schedule": schedule}

  @app.delete("/api/recurring/{schedule_id}")
  def cancel_recurring(schedule_id: str) -> dict:
      with agent_lock:
          found = agent.recurring.cancel_schedule(schedule_id)
          if not found:
              raise HTTPException(status_code=404, detail="Schedule not found")
          agent._save_recurring()
          return {"ok": True}

  @app.put("/api/recurring/{schedule_id}")
  def update_recurring(schedule_id: str, payload: RecurringUpdateRequest) -> dict:
      with agent_lock:
          updates = {k: v for k, v in payload.model_dump().items() if v is not None}
          result = agent.recurring.update_schedule(schedule_id, updates)
          if not result:
              raise HTTPException(status_code=404, detail="Schedule not found")
          agent._save_recurring()
          return {"ok": True, "schedule": result}
  ```

- [ ] **Step 4: Wire recurring chat commands into `main.py`**

  In the intent detection section of `main.py` (near `detect_business_rename`), add a new detector:

  ```python
  def detect_recurring_command(self, user_input: str) -> dict | None:
      lower = user_input.lower()
      # "schedule rent $2000 expense on the 1st every month"
      import re
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
              "frequency": m.group(5).rstrip("s"),  # "months" → "month"
          }
      if "cancel" in lower and "recurring" in lower:
          return {"cancel": True, "raw": user_input}
      if ("show" in lower or "list" in lower) and "recurring" in lower:
          return {"list": True}
      return None
  ```

  In `handle_command_with_metadata`, before the main reasoning loop, check for recurring commands and handle them directly (bypassing AI reasoning for speed):

  ```python
  recurring_cmd = self.detect_recurring_command(user_input)
  if recurring_cmd:
      if recurring_cmd.get("list"):
          schedules = self.recurring.list_schedules()
          msg = f"{len(schedules)} recurring schedule(s) active." if schedules else "No recurring schedules."
          return {"message": msg, "status": self.get_status(), "presentation": None}
      if recurring_cmd.get("cancel"):
          # For simplicity, cancel the first matching schedule by description keyword
          keyword = user_input.lower().replace("cancel", "").replace("recurring", "").strip()
          for s in self.recurring.list_schedules():
              if keyword in s["description"].lower():
                  self.recurring.cancel_schedule(s["id"])
                  self._save_recurring()
                  return {"message": f"Cancelled recurring: {s['description']}.", "status": self.get_status(), "presentation": None}
          return {"message": "No matching recurring schedule found.", "status": self.get_status(), "presentation": None}
      # Create new schedule
      from datetime import date as _date
      import calendar
      today = _date.today()
      day = recurring_cmd["day_of_period"]
      freq = recurring_cmd["frequency"]
      last_day = calendar.monthrange(today.year, today.month)[1]
      start = _date(today.year, today.month, min(day, last_day)).isoformat()
      if start < today.isoformat():
          m2 = today.month % 12 + 1
          y2 = today.year if today.month < 12 else today.year + 1
          last2 = calendar.monthrange(y2, m2)[1]
          start = _date(y2, m2, min(day, last2)).isoformat()
      cat = self.categorization.suggest_category(recurring_cmd["description"])
      category = cat["category"] if cat else "Misc"
      schedule = self.recurring.create_schedule(
          description=recurring_cmd["description"],
          amount=recurring_cmd["amount"],
          category=category,
          entry_type=recurring_cmd["entry_type"],
          frequency=freq + "ly" if not freq.endswith("ly") else freq,
          day_of_period=day,
          start_date=start,
      )
      self._save_recurring()
      return {
          "message": f"Recurring set — {schedule['description']} · ${schedule['amount']:.2f} · {schedule['entry_type']} · {schedule['frequency']} from {schedule['next_date']}.",
          "status": self.get_status(),
          "presentation": None,
      }
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add web_app.py main.py
  git commit -m "feat: recurring API endpoints, status-poll auto-posting, and chat commands"
  ```

---

## Task 8: Recurring UI Section

**Files:**
- Modify: `ui/app.js`

- [ ] **Step 1: Add `fetchRecurring` and `renderRecurring` to `ui/app.js`**

  ```javascript
  function fetchRecurring() {
    fetch('/api/recurring')
      .then(function (r) { return r.json(); })
      .then(function (data) { renderRecurring(data.schedules || []); })
      .catch(function (err) { console.error('fetchRecurring error:', err); });
  }

  function renderRecurring(schedules) {
    var tbody = document.getElementById('recurring-body');
    if (!tbody) { return; }
    tbody.textContent = '';
    if (!schedules.length) {
      var tr = document.createElement('tr');
      var td = document.createElement('td');
      td.colSpan = 6;
      td.style.color = '#6b7280';
      td.style.padding = '1rem';
      td.textContent = 'No recurring schedules. Use Chat to create one.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    schedules.forEach(function (s) {
      var tr = document.createElement('tr');
      [
        s.description,
        (s.entry_type === 'Expense' ? '−' : '+') + '$' + Number(s.amount).toFixed(2),
        s.category,
        s.frequency,
        s.next_date,
      ].forEach(function (val) {
        var td = document.createElement('td');
        td.textContent = val;
        tr.appendChild(td);
      });
      var actionsTd = document.createElement('td');
      var cancelBtn = document.createElement('button');
      cancelBtn.textContent = '✕';
      cancelBtn.style.cssText = 'background:none;border:none;color:#ef4444;cursor:pointer;font-size:1rem';
      cancelBtn.addEventListener('click', function () {
        if (!confirm('Cancel recurring: ' + s.description + '?')) { return; }
        fetch('/api/recurring/' + s.id, { method: 'DELETE' })
          .then(function () { fetchRecurring(); })
          .catch(function (err) { showToast(String(err), 'error'); });
      });
      actionsTd.appendChild(cancelBtn);
      tr.appendChild(actionsTd);
      tbody.appendChild(tr);
    });
  }
  ```

- [ ] **Step 2: Call `fetchRecurring()` in `DOMContentLoaded` and in `initTabs` when recurring tab activated**

  The `initTabs` function already calls `fetchRecurring()` when the recurring tab is clicked (added in Task 1, Step 3). Add an initial call in `DOMContentLoaded` after `fetchStatus()`:

  ```javascript
  fetchStatus();
  fetchRecurring();
  setInterval(fetchStatus, 5000);
  ```

- [ ] **Step 3: Verify end-to-end in browser**

  1. Go to Chat tab, type: `Schedule rent $2000 expense on the 1st every month`
  2. Agent should respond with confirmation
  3. Switch to Recurring tab — rent schedule should appear in the table
  4. Click ✕ — confirm dialog, then row disappears
  5. Verify `memory/long_term/{business_key}/recurring.json` updated on disk

- [ ] **Step 4: Run full test suite**

  ```bash
  pytest tests/ -v
  ```

  Expected: all existing + new tests passing (no regressions)

- [ ] **Step 5: Final commit**

  ```bash
  git add ui/app.js
  git commit -m "feat: recurring transactions UI — table, cancel button, auto-refresh"
  ```

---

## Self-Review

- [x] **Spec coverage:** All Phase 1 requirements covered — sidebar nav, categorization engine (suggest + save + backfill), recurring engine (CRUD + idempotent auto-post + date advance), all 6 API endpoints, chat commands, UI for both features.
- [x] **No placeholders:** Every step has actual code. No "implement X here" stubs.
- [x] **Type consistency:** `RecurringEngine.run_due_schedules` returns `list[dict]` and is used as such in `get_status`. `CategorizationEngine.suggest_category` returns `dict | None` and is guarded with `if cat` before use.
- [x] **Idempotency guard:** `last_posted_date` field prevents double-posting on the same day even if `get_status` is called every 5 seconds.
- [x] **Backwards compatibility:** All existing endpoints and tests untouched. Sidebar uses same `data-tab` routing so existing `initLedger`, `initChat`, etc. all still wire up correctly.
