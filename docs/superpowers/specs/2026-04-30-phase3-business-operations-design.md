# Phase 3 — Business Operations: Implementation Design

**Date:** 2026-04-30
**Status:** Approved
**Parent spec:** `2026-04-27-cpa-agent-features-design.md` (Phase 3 section)

---

## Overview

Phase 3 ships two features: **AR/AP** (Accounts Receivable & Payable) and **Tax Estimates & Deadlines**. Both engine files and API endpoints were partially scaffolded but never committed. This document records the precise bugs, gaps, and implementation steps needed to bring Phase 3 to a shippable state.

---

## Current State (as of 2026-04-30)

### Untracked files (never committed)
- `skills/ar_ap_engine.py` — 148 lines
- `skills/tax_engine.py` — 229 lines
- `tests/test_ar_ap_engine.py` — 253 lines

### Modified but not committed
- `main.py` — Phase 3 imports, instantiation, chat commands added
- `web_app.py` — AR/AP and Tax API endpoints added
- `ui/index.html` — AR/AP and Tax tab sections added
- `ui/app.js` — `fetchArAp`, `renderArAp`, `renderTax` functions added

### What is correct and complete
- `tax_engine.py` — all 5 methods correct: `compute_se_tax`, `compute_estimated_federal`, `get_quarterly_estimate`, `get_irs_deadlines`, `get_upcoming_alerts`, `compute_tax_summary`
- `web_app.py` endpoints — `/api/ar-ap` (GET/POST), `/api/ar-ap/{id}/mark-paid` (PUT), `/api/tax` (GET) are well-structured
- `main.py` — imports, instantiation, `detect_ar_ap_command`, `detect_tax_command` are complete
- `test_ar_ap_engine.py` — all 6 test cases are correct

---

## Bugs to Fix

### Bug 1 — AR/AP schema key inconsistency (`ar_ap_engine.py`)

`add_receivable` stores the contact name under key `"client"`:
```python
new_entry = {"client": client, ...}  # receivable
```
`add_payable` stores it under `"client_vendor"`:
```python
new_entry = {"client_vendor": vendor, ...}  # payable
```

**Impact:** Every consumer (UI, chat handler, `mark_paid`) that reads `client_vendor` crashes for receivables. The `mark_paid` chat handler in `main.py` reads `latest_entry['client_vendor']` — KeyError for receivables.

**Fix:** Unify to `client_vendor` in `add_receivable`. Update the UI renderer (`app.js`) which currently reads `r.client || ''` for receivables.

---

### Bug 2 — `get_upcoming_due` inverted condition (`ar_ap_engine.py:142`)

```python
# Bug: 0 <= r["days_outstanding"] <= -days_ahead  ← always False
upcoming_receivables = [r for r in data["receivables"]
                       if 0 <= r["days_outstanding"] <= -days_ahead and r["status"] == "open"]
```

`days_outstanding` is negative for future due dates (e.g., due in 5 days → `-5`). The correct filter is items not yet overdue but due within the window:

```python
# Fix: -days_ahead <= days_outstanding <= 0  (negative = future, 0 = today)
upcoming_receivables = [r for r in data["receivables"]
                       if -days_ahead <= r["days_outstanding"] <= 0 and r["status"] == "open"]
```

---

### Bug 3 — `mark_paid` does not auto-post to ledger (`ar_ap_engine.py:112`)

The spec requires: "When an AR invoice is marked paid → auto-post Income to ledger. When an AP bill is marked paid → auto-post Expense."

Currently `mark_paid` only updates the status field and adds a comment saying "handled elsewhere" — but nowhere handles it.

**Fix:** `mark_paid` returns a `ledger_row` dict (per the spec signature). The API endpoint `PUT /api/ar-ap/{id}/mark-paid` in `web_app.py` receives this and calls `agent.google_sheets.append_row(ledger_row)`. This keeps the engine pure (no direct sheet access) and the endpoint responsible for the side-effect.

Returned `ledger_row` shape:
```python
{
    "date": paid_date,
    "description": f"{'Invoice paid' if entry_type == 'receivable' else 'Bill paid'}: {entry['client_vendor']}",
    "category": "Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
    "entry_type": "Income" if entry_type == "receivable" else "Expense",
    "amount": entry["amount"],
    "notes": entry.get("notes", "")
}
```

Deduplication guard: check ledger for an existing row matching `(date, description, amount)` before appending.

---

### Bug 4 — Mark Paid button in UI does nothing (`app.js`)

The Mark Paid button in `renderArAp` shows a placeholder toast:
```js
markPaidBtn.addEventListener('click', function () {
  showToast('Mark as paid functionality would be implemented here', 'info');
});
```

**Fix:** Replace with a real API call to `PUT /api/ar-ap/{id}/mark-paid` carrying `{type, paid_date: today}`, then call `fetchArAp()` to refresh the table.

---

## Gaps to Fill

### Gap 1 — Tax UI incomplete (`app.js renderTax`)

`renderTax` only fills in 4 summary metric fields. The spec calls for:
- **Quarterly estimate card** — YTD income → SE tax breakdown → federal tax → total due + due date
- **IRS deadline calendar** — list of Q1–Q4 + Annual deadlines with colour badges:
  - Red = overdue (deadline passed)
  - Blue = upcoming (within 30 days)
  - Grey = future (>30 days away)

The `/api/tax` endpoint already returns `quarterly_estimate`, `deadlines`, and `upcoming_alerts` — only the rendering is missing.

---

### Gap 2 — Tax alerts not in status poll (`main.py` / `web_app.py`)

The spec: "Agent alerts the user in chat when a deadline is within 30 days (checked on status poll)."

`GET /api/status` currently does not call `agent.tax_engine.get_upcoming_alerts()`. Add it to the status response under key `"tax_alerts"`. The existing status-poll handler in `app.js` already shows badge notifications — pipe tax alerts through the same path.

---

### Gap 3 — Dashboard missing AR/AP summary

The spec: "Dashboard shows: open AR total, overdue AR count, upcoming AP due this week."

Add three metric cards to the dashboard section in `index.html` and populate them via a `fetchArAp()` call on dashboard load (reuse the already-written function).

---

### Gap 4 — Missing `test_tax_engine.py`

Need tests for:
- `compute_se_tax` — zero income, positive income
- `compute_estimated_federal` — bracket boundaries
- `get_quarterly_estimate` — correct quarter/due date based on current month
- `get_irs_deadlines` — correct dates for a given year
- `get_upcoming_alerts` — filters correctly by days_ahead
- `compute_tax_summary` — reads ledger rows correctly

---

## Data Flow: mark_paid Auto-Post

```
UI "Mark Paid" button
  → PUT /api/ar-ap/{id}/mark-paid  {type, paid_date}
    → ar_ap_engine.mark_paid(id, type, paid_date)
        → updates status → returns ledger_row dict
    → dedup check against ledger
    → google_sheets.append_row(ledger_row)  [if not duplicate]
  → response: {ok, entry, ledger_posted: bool}
UI refreshes AR/AP table + Ledger tab
```

---

## Implementation Order

| # | Task | File(s) |
|---|------|---------|
| 1 | Fix schema: `client_vendor` unified in `add_receivable` | `ar_ap_engine.py` |
| 2 | Fix `get_upcoming_due` sign logic | `ar_ap_engine.py` |
| 3 | Implement ledger auto-post in `mark_paid` return value | `ar_ap_engine.py` |
| 4 | Wire auto-post in `PUT /api/ar-ap/{id}/mark-paid` endpoint | `web_app.py` |
| 5 | Fix `mark_paid` chat handler key access | `main.py` |
| 6 | Wire Mark Paid button to API + refresh | `app.js` |
| 7 | Complete Tax UI: quarterly card + deadline calendar | `app.js`, `index.html` |
| 8 | Add tax alerts to status poll | `web_app.py`, `main.py` |
| 9 | Add AR/AP dashboard cards | `index.html`, `app.js` |
| 10 | Write `test_tax_engine.py` | `tests/` |
| 11 | Commit all Phase 3 files cleanly | git |

---

## What Does Not Change

- Google Sheet Ledger schema (`Ledger!A:G`) — unchanged
- Existing Phase 1 / Phase 2 endpoints and engines — untouched
- `memory_manager.py` public interface — no new methods needed (engine handles its own file I/O)
- `ar_ap.json` schema — unchanged from parent spec
