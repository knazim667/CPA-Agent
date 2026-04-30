# Phase 3 — Business Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 bugs and fill 4 gaps in the Phase 3 AR/AP + Tax scaffold so both features are correct, fully wired, and tested.

**Architecture:** All changes are additive to existing files — no new files except `tests/test_tax_engine.py`. The AR/AP engine becomes the single schema owner (`client_vendor` key everywhere); the endpoint handles the ledger auto-post side-effect after `mark_paid`; the Tax UI is completed in-place; status poll gains tax alerts; dashboard gains AR/AP summary.

**Tech Stack:** Python 3.11, FastAPI, Vanilla JS (no framework), pytest, Google Sheets API (via existing `record_structured_transaction`)

---

## File Map

| File | Change |
|------|--------|
| `skills/ar_ap_engine.py` | Fix `client_vendor` key in `add_receivable`; fix `get_upcoming_due` sign; no other logic changes |
| `tests/test_ar_ap_engine.py` | Update 3 assertions to match fixed schema |
| `web_app.py` | Wire ledger auto-post inside `mark_ar_ap_paid` endpoint |
| `main.py` | Add `tax_alerts` to `get_status()`; add `ar_ap_summary` to `get_dashboard_snapshot()`; fix `mark_paid` chat handler |
| `ui/index.html` | Fix malformed tax section HTML; add quarterly estimate card + deadline calendar; add 3 AR/AP dashboard metric cards |
| `ui/app.js` | Fix `renderArAp` key for receivables; wire Mark Paid button to API; complete `renderTax`; render AR/AP dashboard cards |
| `tests/test_tax_engine.py` | **Create** — full test coverage for TaxEngine |

---

## Task 1: Fix AR/AP schema — unify `client_vendor` key

**Files:**
- Modify: `skills/ar_ap_engine.py:56-77` (`add_receivable`)
- Modify: `tests/test_ar_ap_engine.py` (3 assertion updates)
- Modify: `ui/app.js` (`renderArAp` receivable row)

The problem: `add_receivable` stores `"client": client` but every consumer (UI, chat handler, `mark_paid`) reads `client_vendor`. Payables already use `client_vendor`. Fix the receivable to match.

- [ ] **Step 1: Update `test_add_receivable` to assert the correct key (test will fail until engine is fixed)**

In `tests/test_ar_ap_engine.py`, find `test_add_receivable` and change:
```python
# OLD
assert result["client"] == "Test Client"
# NEW
assert result["client_vendor"] == "Test Client"
```

- [ ] **Step 2: Update `test_get_ar_ap` fixture and assertion**

In `tests/test_ar_ap_engine.py`, find `test_get_ar_ap`. Update the test data fixture:
```python
# OLD  (inside test_data["receivables"][0])
"client": "Client 1",
# NEW
"client_vendor": "Client 1",
```
And update the assertion:
```python
# OLD
assert result["receivables"][0]["client"] == "Client 1"
# NEW
assert result["receivables"][0]["client_vendor"] == "Client 1"
```

- [ ] **Step 3: Update `test_get_upcoming_due` assertion**

In `tests/test_ar_ap_engine.py`, find `test_get_upcoming_due` and change:
```python
# OLD
assert result["receivables"][0]["client"] == "Soon Client"
# NEW
assert result["receivables"][0]["client_vendor"] == "Soon Client"
```

- [ ] **Step 4: Run the three updated tests — confirm they fail**

```bash
cd /Users/muhammadnazam/Documents/CPA-Agent
python -m pytest tests/test_ar_ap_engine.py::test_add_receivable tests/test_ar_ap_engine.py::test_get_ar_ap tests/test_ar_ap_engine.py::test_get_upcoming_due -v
```
Expected: FAIL with `KeyError: 'client_vendor'`

- [ ] **Step 5: Fix `add_receivable` in `ar_ap_engine.py`**

In `skills/ar_ap_engine.py`, replace the `new_entry` dict inside `add_receivable` (around line 62):
```python
# OLD
new_entry = {
    "id": entry_id,
    "client": client,
    "amount": amount,
    "due_date": due_date,
    "issue_date": issue_date,
    "status": "open",
    "notes": notes,
    "entry_type": "receivable"
}
# NEW
new_entry = {
    "id": entry_id,
    "client_vendor": client,
    "amount": amount,
    "due_date": due_date,
    "issue_date": issue_date,
    "status": "open",
    "notes": notes,
    "entry_type": "receivable"
}
```

- [ ] **Step 6: Fix `renderArAp` in `app.js` to read `client_vendor` for receivables**

In `ui/app.js`, find the receivables `forEach` inside `renderArAp` and change:
```javascript
// OLD
r.client || '',
// NEW
r.client_vendor || '',
```

- [ ] **Step 7: Run all ar_ap tests — confirm they pass**

```bash
python -m pytest tests/test_ar_ap_engine.py -v
```
Expected: all 6 tests PASS

- [ ] **Step 8: Commit**

```bash
git add skills/ar_ap_engine.py tests/test_ar_ap_engine.py ui/app.js
git commit -m "fix: unify AR/AP schema to client_vendor key for receivables"
```

---

## Task 2: Fix `get_upcoming_due` sign logic

**Files:**
- Modify: `skills/ar_ap_engine.py:139-146` (`get_upcoming_due`)

The problem: `days_outstanding` is negative for future dates (e.g., due in 5 days → `-5`). The current filter `0 <= days_outstanding <= -days_ahead` has a negative upper bound and can never be true.

- [ ] **Step 1: Run `test_get_upcoming_due` — confirm it fails**

```bash
python -m pytest tests/test_ar_ap_engine.py::test_get_upcoming_due -v
```
Expected: FAIL — `assert len(result["receivables"]) == 1` fails (filter returns 0 items).

- [ ] **Step 2: Fix the filter in `get_upcoming_due`**

In `skills/ar_ap_engine.py`, replace the body of `get_upcoming_due` entirely:
```python
def get_upcoming_due(self, days_ahead: int = 7) -> Dict[str, List[Dict]]:
    """Get items due within the next N days (not yet overdue)."""
    data = self.get_ar_ap()
    upcoming_receivables = [
        r for r in data["receivables"]
        if -days_ahead <= r["days_outstanding"] <= 0 and r["status"] == "open"
    ]
    upcoming_payables = [
        p for p in data["payables"]
        if -days_ahead <= p["days_outstanding"] <= 0 and p["status"] == "open"
    ]
    return {
        "receivables": upcoming_receivables,
        "payables": upcoming_payables,
    }
```

- [ ] **Step 3: Run all ar_ap tests**

```bash
python -m pytest tests/test_ar_ap_engine.py -v
```
Expected: all 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add skills/ar_ap_engine.py
git commit -m "fix: correct get_upcoming_due sign logic for future due dates"
```

---

## Task 3: Wire ledger auto-post on mark_paid

**Files:**
- Modify: `web_app.py` — `mark_ar_ap_paid` endpoint (~line 688)
- Modify: `main.py` — `mark_paid` chat handler (~line 1530)

When an AR entry is marked paid, auto-post an Income transaction to the ledger. When an AP entry is marked paid, auto-post an Expense. The endpoint calls the existing `agent.record_structured_transaction` which has a built-in dedup guard.

- [ ] **Step 1: Update `mark_ar_ap_paid` in `web_app.py`**

Find `def mark_ar_ap_paid` and replace its body with:
```python
@app.put("/api/ar-ap/{entry_id}/mark-paid")
def mark_ar_ap_paid(entry_id: str, payload: dict) -> dict:
    with agent_lock:
        try:
            from datetime import datetime as _dt
            entry_type = payload.get("type", "receivable").lower()
            paid_date = payload.get("paid_date") or _dt.now().strftime("%Y-%m-%d")

            if entry_type not in ["receivable", "payable"]:
                raise HTTPException(status_code=400, detail="Type must be 'receivable' or 'payable'")

            entry = agent.ar_ap_engine.mark_paid(
                entry_id=entry_id,
                entry_type=entry_type,
                paid_date=paid_date,
            )

            description = (
                f"Invoice paid: {entry['client_vendor']}"
                if entry_type == "receivable"
                else f"Bill paid: {entry['client_vendor']}"
            )
            post_result = agent.record_structured_transaction(
                date=paid_date,
                description=description,
                category="Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
                amount=entry["amount"],
                entry_type="Income" if entry_type == "receivable" else "Expense",
                notes=entry.get("notes", ""),
            )
            return {"ok": True, "entry": entry, "ledger_posted": post_result.get("ok", False)}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 2: Fix `mark_paid` chat handler in `main.py`**

Find the `elif action == "mark_paid":` block inside `handle_command_with_metadata` and replace it:
```python
elif action == "mark_paid":
    from datetime import date as _date_cls
    entry_type = ar_ap_cmd.get("entry_type", "receivable")
    data = self.ar_ap_engine.get_ar_ap()
    collection = "receivables" if entry_type == "receivable" else "payables"
    open_entries = [e for e in data[collection] if e["status"] == "open"]
    if not open_entries:
        return {
            "message": f"No open {entry_type} entries found to mark as paid.",
            "status": self.get_status(),
            "presentation": None,
        }
    latest_entry = max(open_entries, key=lambda x: x["issue_date"])
    paid_date = _date_cls.today().isoformat()
    self.ar_ap_engine.mark_paid(
        entry_id=latest_entry["id"],
        entry_type=entry_type,
        paid_date=paid_date,
    )
    description = (
        f"Invoice paid: {latest_entry['client_vendor']}"
        if entry_type == "receivable"
        else f"Bill paid: {latest_entry['client_vendor']}"
    )
    self.record_structured_transaction(
        date=paid_date,
        description=description,
        category="Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
        amount=latest_entry["amount"],
        entry_type="Income" if entry_type == "receivable" else "Expense",
        notes=latest_entry.get("notes", ""),
    )
    return {
        "message": f"Marked {entry_type} '{latest_entry['client_vendor']}' as paid and posted to ledger.",
        "status": self.get_status(),
        "presentation": None,
    }
```

- [ ] **Step 3: Commit**

```bash
git add web_app.py main.py
git commit -m "feat: auto-post Income/Expense to ledger when AR/AP marked paid"
```

---

## Task 4: Wire Mark Paid button in the UI

**Files:**
- Modify: `ui/app.js` — Mark Paid button handlers inside `renderArAp`

The button currently shows a toast placeholder. Replace it with a real API call for both the receivables and payables sections.

- [ ] **Step 1: Replace the receivables Mark Paid button handler**

In `ui/app.js`, inside `renderArAp`, find the receivables Mark Paid handler:
```javascript
markPaidBtn.addEventListener('click', function () {
  showToast('Mark as paid functionality would be implemented here', 'info');
});
```

Replace with:
```javascript
markPaidBtn.addEventListener('click', function () {
  var today = new Date().toISOString().split('T')[0];
  fetch('/api/ar-ap/' + r.id + '/mark-paid', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: r.entry_type, paid_date: today }),
  })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (data.ok) {
        var msg = data.ledger_posted ? 'Marked as paid and posted to ledger.' : 'Marked as paid.';
        showToast(msg, 'success');
        fetchArAp();
      } else {
        showToast('Error: ' + (data.detail || 'Unknown error'), 'error');
      }
    })
    .catch(function (err) { showToast('Network error: ' + err, 'error'); });
});
```

- [ ] **Step 2: Find and replace the payables Mark Paid handler the same way**

The payables section has an identical toast placeholder. Apply the same replacement, substituting `p` for `r` (since payables forEach uses variable `p`):
```javascript
markPaidBtn.addEventListener('click', function () {
  var today = new Date().toISOString().split('T')[0];
  fetch('/api/ar-ap/' + p.id + '/mark-paid', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: p.entry_type, paid_date: today }),
  })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (data.ok) {
        var msg = data.ledger_posted ? 'Marked as paid and posted to ledger.' : 'Marked as paid.';
        showToast(msg, 'success');
        fetchArAp();
      } else {
        showToast('Error: ' + (data.detail || 'Unknown error'), 'error');
      }
    })
    .catch(function (err) { showToast('Network error: ' + err, 'error'); });
});
```

- [ ] **Step 3: Commit**

```bash
git add ui/app.js
git commit -m "feat: wire AR/AP Mark Paid button to PUT /api/ar-ap/{id}/mark-paid"
```

---

## Task 5: Write `test_tax_engine.py`

**Files:**
- Create: `tests/test_tax_engine.py`

- [ ] **Step 1: Create `tests/test_tax_engine.py`**

```python
import pytest
from datetime import date, timedelta
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))
from tax_engine import TaxEngine


class MockMemoryManager:
    current_business_key = "test_business"

    def get_current_business(self):
        return {"business_name": "Test Business"}


@pytest.fixture
def engine():
    return TaxEngine(MockMemoryManager())


def test_compute_se_tax_zero_income(engine):
    assert engine.compute_se_tax(0) == 0.0
    assert engine.compute_se_tax(-100) == 0.0


def test_compute_se_tax_positive(engine):
    result = engine.compute_se_tax(10000)
    expected = round(10000 * 0.9235 * 0.153, 10)
    assert abs(result - expected) < 0.01


def test_compute_estimated_federal_zero(engine):
    assert engine.compute_estimated_federal(0) == 0.0
    assert engine.compute_estimated_federal(-50) == 0.0


def test_compute_estimated_federal_first_bracket(engine):
    # $5,000 is entirely in the 10% bracket
    result = engine.compute_estimated_federal(5000)
    assert abs(result - 500.0) < 0.01


def test_compute_estimated_federal_second_bracket(engine):
    # $20,000: $11,600 @ 10% + $8,400 @ 12%
    result = engine.compute_estimated_federal(20000)
    expected = 11600 * 0.10 + (20000 - 11600) * 0.12
    assert abs(result - expected) < 0.01


def test_compute_estimated_federal_third_bracket(engine):
    # $60,000: spans 10%, 12%, 22% brackets
    result = engine.compute_estimated_federal(60000)
    expected = (
        11600 * 0.10
        + (47300 - 11600) * 0.12
        + (60000 - 47300) * 0.22
    )
    assert abs(result - expected) < 0.01


def test_get_quarterly_estimate_structure(engine):
    result = engine.get_quarterly_estimate(50000, 2026)
    assert "se_tax" in result
    assert "federal_tax" in result
    assert "total" in result
    assert "due_date" in result
    assert "quarter" in result
    assert result["total"] == round(result["se_tax"] + result["federal_tax"], 2)


def test_get_quarterly_estimate_quarter_logic(engine):
    # Today is 2026-04-30 — April is month 4, <= 5, so Q2 due June 15
    result = engine.get_quarterly_estimate(40000, 2026)
    assert result["quarter"] == "Q2"
    assert result["due_date"] == "2026-06-15"


def test_get_irs_deadlines_count(engine):
    deadlines = engine.get_irs_deadlines(2026)
    assert len(deadlines) == 5  # Q1, Q2, Q3, Q4, Annual


def test_get_irs_deadlines_dates(engine):
    deadlines = engine.get_irs_deadlines(2026)
    by_quarter = {d["quarter"]: d["deadline"] for d in deadlines}
    assert by_quarter["Q1"] == "2026-04-15"
    assert by_quarter["Q2"] == "2026-06-15"
    assert by_quarter["Q3"] == "2026-09-15"
    assert by_quarter["Q4"] == "2027-01-15"
    assert by_quarter["Annual"] == "2027-04-15"


def test_get_upcoming_alerts_excludes_far_deadlines(engine):
    # Q2 deadline is 2026-06-15; today is 2026-04-30 = 46 days away => NOT within 30 days
    alerts = engine.get_upcoming_alerts(days_ahead=30)
    quarters = [a["quarter"] for a in alerts]
    assert "Q2" not in quarters


def test_get_upcoming_alerts_within_window(engine):
    # 60 days captures Q2 (June 15 = 46 days from Apr 30)
    alerts = engine.get_upcoming_alerts(days_ahead=60)
    quarters = [a["quarter"] for a in alerts]
    assert "Q2" in quarters


def test_compute_tax_summary_empty_ledger(engine):
    result = engine.compute_tax_summary([])
    assert result["total_income"] == 0.0
    assert result["total_expenses"] == 0.0
    assert result["net_income"] == 0.0
    assert result["se_tax"] == 0.0
    assert result["federal_tax"] == 0.0
    assert result["total_tax"] == 0.0


def test_compute_tax_summary_reads_ledger_rows(engine):
    rows = [
        ["2026-01-15", "Client A", "Revenue", "Income", 5000, "", ""],
        ["2026-02-01", "Office Rent", "Rent", "Expense", 1000, "", ""],
        ["2026-03-01", "Client B", "Revenue", "Income", 3000, "", ""],
    ]
    result = engine.compute_tax_summary(rows)
    assert result["total_income"] == 8000.0
    assert result["total_expenses"] == 1000.0
    assert result["net_income"] == 7000.0
    assert result["se_tax"] > 0
    assert result["federal_tax"] > 0
    assert result["estimated_quarterly_payment"] == round(result["total_tax"] / 4, 2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run the tests**

```bash
python -m pytest tests/test_tax_engine.py -v
```
Expected: all 13 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_tax_engine.py
git commit -m "test: add full test coverage for TaxEngine"
```

---

## Task 6: Complete Tax UI — quarterly card + deadline calendar

**Files:**
- Modify: `ui/index.html` — fix malformed `tax-total-tax` div; add quarterly estimate card + deadline calendar
- Modify: `ui/app.js` — replace `renderTax` with complete implementation

The existing HTML has an unclosed `<div class="metric-value" id="tax-total-tax">—</div` (missing closing `>`) which swallows the chat tab into the tax section.

- [ ] **Step 1: Fix the malformed HTML and extend the Tax section in `index.html`**

Find this exact block in `ui/index.html`:
```html
              <div class="panel" style="flex:1;min-width:160px;text-align:center">
                <div class="metric-value" id="tax-total-tax">—</div

        <!-- Chat tab -->
```

Replace with:
```html
              <div class="panel" style="flex:1;min-width:160px;text-align:center">
                <div class="metric-value" id="tax-total-tax">—</div>
                <div style="font-size:0.78rem;color:#64748b">Total Tax</div>
              </div>
            </div>

            <div class="panel" style="margin-bottom:1rem">
              <h3 style="margin-top:0;font-size:1rem">Next Quarterly Estimate</h3>
              <div style="display:flex;gap:2rem;flex-wrap:wrap">
                <div>Quarter: <strong id="tax-quarter">—</strong></div>
                <div>Due: <strong id="tax-due-date">—</strong></div>
                <div>SE Tax: <strong id="tax-q-se-tax">—</strong></div>
                <div>Federal: <strong id="tax-q-federal">—</strong></div>
                <div>Total Due: <strong id="tax-q-total" style="color:#dc2626">—</strong></div>
              </div>
            </div>

            <div class="panel">
              <h3 style="margin-top:0;font-size:1rem">IRS Deadline Calendar</h3>
              <table class="ledger-table">
                <thead>
                  <tr><th>Quarter</th><th>Description</th><th>Due Date</th><th>Status</th></tr>
                </thead>
                <tbody id="tax-deadlines-body"></tbody>
              </table>
            </div>
          </div>

        <!-- Chat tab -->
```

- [ ] **Step 2: Replace `renderTax` in `app.js` with a complete implementation**

Find `function renderTax(data)` and replace the entire function:
```javascript
function renderTax(data) {
  var summary = data.tax_summary || {};
  var estimate = data.quarterly_estimate || {};
  var deadlines = data.deadlines || [];
  var taxOutput = document.getElementById('tax-output');

  var netIncomeEl = document.getElementById('tax-net-income');
  var seTaxEl = document.getElementById('tax-se-tax');
  var federalTaxEl = document.getElementById('tax-federal-tax');
  var totalTaxEl = document.getElementById('tax-total-tax');
  if (netIncomeEl) netIncomeEl.textContent = '$' + Number(summary.net_income || 0).toFixed(2);
  if (seTaxEl) seTaxEl.textContent = '$' + Number(summary.se_tax || 0).toFixed(2);
  if (federalTaxEl) federalTaxEl.textContent = '$' + Number(summary.federal_tax || 0).toFixed(2);
  if (totalTaxEl) totalTaxEl.textContent = '$' + Number(summary.total_tax || 0).toFixed(2);

  var quarterEl = document.getElementById('tax-quarter');
  var dueDateEl = document.getElementById('tax-due-date');
  var qSeEl = document.getElementById('tax-q-se-tax');
  var qFedEl = document.getElementById('tax-q-federal');
  var qTotalEl = document.getElementById('tax-q-total');
  if (quarterEl) quarterEl.textContent = estimate.quarter || '—';
  if (dueDateEl) dueDateEl.textContent = estimate.due_date || '—';
  if (qSeEl) qSeEl.textContent = '$' + Number(estimate.se_tax || 0).toFixed(2);
  if (qFedEl) qFedEl.textContent = '$' + Number(estimate.federal_tax || 0).toFixed(2);
  if (qTotalEl) qTotalEl.textContent = '$' + Number(estimate.total || 0).toFixed(2);

  var deadlinesBody = document.getElementById('tax-deadlines-body');
  if (deadlinesBody) {
    deadlinesBody.textContent = '';
    var now = new Date();
    deadlines.forEach(function (d) {
      var tr = document.createElement('tr');
      var deadlineDate = new Date(d.deadline + 'T00:00:00');
      var daysUntil = Math.round((deadlineDate - now) / (1000 * 60 * 60 * 24));
      var badge, color;
      if (daysUntil < 0) {
        badge = 'Overdue'; color = '#dc2626';
      } else if (daysUntil <= 30) {
        badge = 'Upcoming'; color = '#2563eb';
      } else {
        badge = 'Future'; color = '#64748b';
      }
      [d.quarter, d.description, d.deadline].forEach(function (val) {
        var td = document.createElement('td');
        td.textContent = val;
        tr.appendChild(td);
      });
      var statusTd = document.createElement('td');
      var statusSpan = document.createElement('span');
      statusSpan.textContent = badge;
      statusSpan.style.color = color;
      statusSpan.style.fontWeight = '600';
      statusTd.appendChild(statusSpan);
      tr.appendChild(statusTd);
      deadlinesBody.appendChild(tr);
    });
  }

  if (taxOutput) taxOutput.classList.remove('hidden');
}
```

Note: status badge uses `document.createElement` + `textContent` instead of `innerHTML` to avoid XSS.

- [ ] **Step 3: Commit**

```bash
git add ui/index.html ui/app.js
git commit -m "feat: complete Tax UI with quarterly estimate card and IRS deadline calendar"
```

---

## Task 7: Add tax alerts to status poll

**Files:**
- Modify: `main.py` — `get_status()` method (~line 767)

The spec requires tax deadline alerts (within 30 days) to be surfaced in every status poll response.

- [ ] **Step 1: Add `tax_alerts` to `get_status()` in `main.py`**

Find the `return {` at the end of `get_status()` and add the `tax_alerts` collection before it:
```python
    tax_alerts = []
    try:
        tax_alerts = self.tax_engine.get_upcoming_alerts(days_ahead=30)
    except Exception:  # noqa: BLE001
        pass

    short_term = self.memory.load_short_term_context()
    current = self.memory.get_current_business()
    return {
        "active_business_key": self.memory.current_business_key,
        "active_business": current,
        "businesses": self.list_businesses(),
        "conversation": short_term.get("conversation", []),
        "workspace_boot_error": self.workspace_boot_error,
        "input_mode": self.input_mode,
        "model_config": self.get_model_status(),
        "dashboard": self.get_dashboard_snapshot(),
        "learned_source_count": len(self.memory.load_learned_sources().get("entries", [])),
        "tax_alerts": tax_alerts,
    }
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add tax deadline alerts to status poll response"
```

---

## Task 8: Add AR/AP summary to dashboard

**Files:**
- Modify: `main.py` — `get_dashboard_snapshot()` (~line 729)
- Modify: `ui/index.html` — dashboard metrics grid
- Modify: `ui/app.js` — status handler that populates dashboard metric cards

The spec requires: open AR total (dollar value), overdue AR count, upcoming AP count (due this week).

- [ ] **Step 1: Add `ar_ap_summary` to `get_dashboard_snapshot()` in `main.py`**

Inside `get_dashboard_snapshot()`, add before the final `return` statement:
```python
        ar_ap_summary = {"open_ar_total": 0.0, "overdue_ar_count": 0, "upcoming_ap_count": 0}
        try:
            ar_ap_data = self.ar_ap_engine.get_ar_ap()
            ar_ap_summary["open_ar_total"] = round(
                sum(r["amount"] for r in ar_ap_data["receivables"] if r["status"] == "open"), 2
            )
            ar_ap_summary["overdue_ar_count"] = len([
                r for r in ar_ap_data["receivables"]
                if r["days_outstanding"] > 0 and r["status"] == "open"
            ])
            ar_ap_summary["upcoming_ap_count"] = len([
                p for p in ar_ap_data["payables"]
                if -7 <= p["days_outstanding"] <= 0 and p["status"] == "open"
            ])
        except Exception:  # noqa: BLE001
            pass
```

Add `"ar_ap_summary": ar_ap_summary` to the return dict alongside existing keys.

- [ ] **Step 2: Add 3 AR/AP metric cards to the dashboard `metrics-grid` in `index.html`**

Find the closing `</div>` of the last existing `metric-card` (the Flagged card) in the dashboard section. Add the three new cards after it, before the closing `</div>` of `metrics-grid`:
```html
            <div class="metric-card">
              <p class="metric-label">Open AR</p>
              <span id="metric-open-ar" class="metric-value skeleton">—</span>
            </div>
            <div class="metric-card">
              <p class="metric-label">Overdue AR</p>
              <span id="metric-overdue-ar" class="metric-value skeleton">—</span>
            </div>
            <div class="metric-card">
              <p class="metric-label">AP Due (7d)</p>
              <span id="metric-upcoming-ap" class="metric-value skeleton">—</span>
            </div>
```

- [ ] **Step 3: Populate the new cards in `app.js`**

Find the block in `app.js` where `var dash = status.dashboard || {}` is set and dashboard metrics are populated (around `metricIncome.textContent = ...`). Add after the existing metric assignments:
```javascript
    var arApSummary = dash.ar_ap_summary || {};
    var metricOpenAr = document.getElementById('metric-open-ar');
    var metricOverdueAr = document.getElementById('metric-overdue-ar');
    var metricUpcomingAp = document.getElementById('metric-upcoming-ap');
    if (metricOpenAr) {
      metricOpenAr.textContent = arApSummary.open_ar_total !== undefined
        ? fmt(arApSummary.open_ar_total) : '—';
    }
    if (metricOverdueAr) {
      metricOverdueAr.textContent = arApSummary.overdue_ar_count !== undefined
        ? arApSummary.overdue_ar_count : '—';
    }
    if (metricUpcomingAp) {
      metricUpcomingAp.textContent = arApSummary.upcoming_ap_count !== undefined
        ? arApSummary.upcoming_ap_count : '—';
    }
```

- [ ] **Step 4: Commit**

```bash
git add main.py ui/index.html ui/app.js
git commit -m "feat: add AR/AP summary cards (open AR, overdue AR, upcoming AP) to dashboard"
```

---

## Task 9: Stage and commit all remaining untracked Phase 3 files

All prior tasks commit individual changes. This final task stages the originally-untracked scaffold files (`ar_ap_engine.py`, `tax_engine.py`, `test_ar_ap_engine.py`) which carry the cumulative fixes from Tasks 1–4, and verifies the full test suite is green.

- [ ] **Step 1: Check what is still untracked**

```bash
git status
```
Expected untracked: `skills/ar_ap_engine.py`, `skills/tax_engine.py`, `tests/test_ar_ap_engine.py`, `memory/long_term/Business_A/category_rules.json`

- [ ] **Step 2: Run the full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 3: Stage and commit remaining untracked files**

```bash
git add skills/ar_ap_engine.py skills/tax_engine.py tests/test_ar_ap_engine.py
git add memory/long_term/Business_A/category_rules.json
git commit -m "feat: commit Phase 3 engines and tests — AR/AP and Tax (all bugs fixed)"
```

- [ ] **Step 4: Confirm clean state**

```bash
git status
git log --oneline -10
```
Expected: working tree clean; Phase 3 commits visible in log.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|-----------------|------|
| Bug 1 — `client_vendor` unified | Task 1 |
| Bug 2 — `get_upcoming_due` sign | Task 2 |
| Bug 3 — ledger auto-post on `mark_paid` | Task 3 |
| Bug 4 — `mark_paid` chat handler key | Task 3 |
| Gap 1 — Mark Paid button calls API | Task 4 |
| Missing `test_tax_engine.py` | Task 5 |
| Gap 2 — Tax UI quarterly + calendar | Task 6 |
| Gap 3 — Tax alerts in status poll | Task 7 |
| Gap 4 — AR/AP dashboard summary | Task 8 |
| Commit all Phase 3 untracked files | Task 9 |

**Placeholder scan:** No TBD/TODO — every step has exact code, exact commands, exact expected output.

**Type consistency:**
- `client_vendor` key introduced in Task 1 used in Tasks 3, 4, 8 — consistent throughout.
- `get_ar_ap()` public method used in Tasks 2 and 8 (not `_load_data()`) — consistent.
- `record_structured_transaction(date, description, category, amount, entry_type, notes)` signature matches `main.py:405` in both the endpoint (Task 3) and the chat handler fix (Task 3).
- `ar_ap_summary` dict keys (`open_ar_total`, `overdue_ar_count`, `upcoming_ap_count`) match between `main.py` (Task 8 Step 1) and `app.js` (Task 8 Step 3).
- `tax_alerts` key added to `get_status()` return in Task 7.
- `ledger_posted` response key from the endpoint (Task 3) consumed by the UI button handler (Task 4).
