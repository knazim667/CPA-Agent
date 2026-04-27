# CPA-Agent Feature Expansion — Design Spec

**Date:** 2026-04-27
**Status:** Approved

---

## Overview

Add 8 accounting features to CPA-Agent in three phased releases. The Google Sheet Ledger (`Ledger!A:G`) remains the single source of truth for all transactions; every new report and engine reads from it rather than maintaining its own transaction store.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| AI Categorization approach | Hybrid (suggest + remember corrections) | Zero setup, transparent, self-improving |
| Recurring transaction setup | Chat creates, UI manages | Fastest to create; visual management for edits/cancels |
| Navigation structure | Left sidebar with grouped sections | Scales to 13+ items; matches QuickBooks/Xero pattern |

---

## Navigation Structure

Left sidebar replaces the current top tab bar. Sections:

```
[Business name + switcher]

Dashboard

BOOKS
  Ledger
  Recurring          ← new

REPORTS
  P&L
  Balance Sheet      ← new
  Cash Flow          ← new
  Budget             ← new

OPERATIONS
  AR / AP            ← new
  Reconcile          ← new
  Tax                ← new

TOOLS
  Documents
  Chat
```

The sidebar is always visible on desktop. The top bar retains the model badge and settings gear only.

---

## Phase 1 — Smart Foundation (~2 weeks)

### Feature 1: AI Smart Categorization (Hybrid)

**Behaviour:**
- On every transaction entry (chat, form, document upload, recurring auto-post), the agent checks `memory/long_term/{business_key}/category_rules.json` for a vendor→category rule matching the description.
- If a rule matches: category is auto-filled and shown with a ✦ badge in the Ledger.
- If no rule matches: category field shows "Uncategorized" in yellow, prompting user input.
- When the user sets or corrects a category, the rule is saved to `memory/long_term/{business_key}/category_rules.json` automatically — no manual rule writing required.
- On first run, the agent back-fills rules by scanning existing ledger history for repeated vendor+category pairs.

**Rule schema (`memory/long_term/{business_key}/category_rules.json`):**
```json
{
  "rules": [
    {
      "id": "uuid",
      "pattern": "starbucks",
      "match_type": "contains",
      "category": "Meals & Entertainment",
      "confidence": 0.95,
      "created_at": "2026-04-27",
      "use_count": 12
    }
  ]
}
```

**New file:** `skills/categorization_engine.py`
- `suggest_category(description: str) -> dict | None` — returns `{category, confidence, rule_id}` or None
- `save_rule(description: str, category: str) -> dict` — normalises description to pattern, saves/updates rule
- `backfill_rules_from_ledger(rows: list[list]) -> int` — scans existing rows, creates rules for repeated pairs

**UI changes:**
- Ledger category column shows ✦ green badge for AI-suggested, yellow for uncategorised
- Clicking the category badge opens an inline dropdown to accept/correct
- Correction triggers `POST /api/category-rule` and re-renders the cell

**New endpoints:**
- `GET /api/category/suggest?description=<text>` → `{category, confidence}`
- `POST /api/category-rule` body `{description, category}` → saves rule

---

### Feature 2: Recurring Transactions

**Behaviour:**
- User creates a recurring entry via chat: *"Schedule rent $2000 expense on the 1st every month"*
- Agent parses: description, amount, category (via categorization engine), frequency (`daily|weekly|monthly|annually`), day-of-period, start date
- Entry saved to `memory/long_term/{business_key}/recurring.json`
- On every `GET /api/status` call (polling every 5 seconds), the recurring engine checks if any schedule's `next_date` equals today — if so, auto-posts the transaction to the ledger and advances `next_date`
- No external cron job required

**Schedule schema (`memory/long_term/{business_key}/recurring.json`):**
```json
{
  "schedules": [
    {
      "id": "uuid",
      "description": "Office Rent",
      "amount": 2000.00,
      "category": "Rent",
      "entry_type": "Expense",
      "frequency": "monthly",
      "day_of_period": 1,
      "next_date": "2026-05-01",
      "active": true,
      "created_at": "2026-04-27"
    }
  ]
}
```

**New file:** `skills/recurring_engine.py`
- `create_schedule(description, amount, category, entry_type, frequency, day_of_period, start_date) -> dict`
- `run_due_schedules(agent) -> list[dict]` — called on each status poll; posts due entries and advances next_date
- `cancel_schedule(schedule_id) -> bool`
- `update_schedule(schedule_id, updates: dict) -> dict`
- `list_schedules() -> list[dict]`

**UI — Recurring section (sidebar: Books → Recurring):**
- Table: Description / Amount / Category / Frequency / Next Date / Edit / Cancel
- "Add via Chat" hint at bottom
- Dashboard shows "Scheduled This Month" summary card

**New endpoints:**
- `GET /api/recurring` → list of active schedules
- `POST /api/recurring` body `{description, amount, category, entry_type, frequency, day_of_period, start_date}`
- `DELETE /api/recurring/{id}`
- `PUT /api/recurring/{id}` body partial updates

**Chat commands wired in `main.py`:**
- *"Schedule [description] $[amount] [type] on the [N]th every [frequency]"*
- *"Cancel [description] recurring"*
- *"Show recurring schedules"*

---

## Phase 2 — Complete the Books (~3–4 weeks)

### Feature 3: Balance Sheet & Cash Flow

**Behaviour:**
- Both statements are computed on-demand by reading `Ledger!A:G`
- No separate transaction store — ledger is the source of truth
- Balance Sheet uses simplified defaults for a single-ledger model: Cash ≈ net income YTD (a reasonable proxy when no bank account balance is tracked separately); AR = open receivables from `ar_ap.json` when that file exists (Phase 3), otherwise AR = 0. This simplification is documented in the UI with a tooltip.
- The balance check (Assets = Liabilities + Equity) will only hold exactly once AR/AP data exists in Phase 3; in Phase 2 the sheet will show a note: "AR/AP data not yet available — Balance Sheet is approximate."
- Cash Flow groups ledger rows into Operating / Investing / Financing by category

**New file:** `skills/financial_statements.py`
- `compute_balance_sheet(ledger_rows, ar_ap_data) -> dict` — returns `{assets, liabilities, equity, balanced: bool}`
- `compute_cash_flow(ledger_rows, period_start, period_end) -> dict` — returns `{operating, investing, financing, net_change}`

**UI — Reports → Balance Sheet / Cash Flow:**
- Balance Sheet: three columns (Assets / Liabilities / Equity) with balance check shown
- Cash Flow: three activity sections + net change summary
- Date range picker; Export PDF button (uses browser print)

**New endpoints:**
- `GET /api/balance-sheet?from=&to=`
- `GET /api/cash-flow?from=&to=`

---

### Feature 4: Budget vs. Actual

**Behaviour:**
- User sets budgets via chat: *"Set marketing budget $1000 per month"*
- Budgets stored in `memory/budgets.json` keyed by business + category + period
- Actuals computed live from ledger rows matching the category + period
- Alerts fire at 80% and 100% utilisation — shown in Dashboard and Budget section
- Budget alerts included in `GET /api/status` response so polling picks them up automatically

**Budget schema (`memory/budgets.json`):**
```json
{
  "budgets": [
    {
      "id": "uuid",
      "category": "Marketing",
      "amount": 1000.00,
      "period": "monthly",
      "business_key": "nazam_llc",
      "created_at": "2026-04-27"
    }
  ]
}
```

**New file:** `skills/budget_engine.py`
- `set_budget(category, amount, period, business_key) -> dict`
- `compute_actuals(budgets, ledger_rows, month) -> list[dict]` — each item has `{category, budget, actual, remaining, pct}`
- `get_alerts(actuals) -> list[dict]` — items where `pct >= 0.8`

**UI — Reports → Budget:**
- Table: Category / Budget / Actual / Remaining / Progress bar
- Progress bar: green <80%, amber 80–99%, red ≥100%
- Set budget inline or via chat

**New endpoints:**
- `GET /api/budget?month=YYYY-MM`
- `POST /api/budget` body `{category, amount, period}`
- `DELETE /api/budget/{id}`

---

### Feature 5: Bank Reconciliation

**Behaviour:**
- User uploads a bank statement (CSV or PDF) via the Reconcile section
- `reconciliation_engine` parses it into rows `{date, description, amount}`
- Each bank row is matched against ledger rows by date (±1 day) and amount (exact)
- Matched rows are marked reconciled; unmatched rows are returned to the UI for manual action
- User can: add unmatched bank row to ledger, or mark as already accounted for
- Difference (bank balance vs ledger balance) shown at top

**New file:** `skills/reconciliation_engine.py`
- `parse_bank_statement(file_path: Path) -> list[dict]` — handles CSV and PDF (uses existing DocumentProcessor for PDF)
- `match_transactions(bank_rows, ledger_rows, tolerance_days=1) -> dict` — returns `{matched, unmatched_bank, unmatched_ledger}`
- `compute_difference(bank_balance, ledger_balance) -> float`

**UI — Operations → Reconcile:**
- Upload zone for bank statement
- Three-tile summary: Bank Balance / Ledger Balance / Difference
- Unmatched table with "Add to ledger" and "Mark resolved" actions per row

**New endpoints:**
- `POST /api/reconcile/upload` multipart file
- `POST /api/reconcile/resolve/{id}` body `{action: "add_to_ledger" | "mark_resolved"}`

---

## Phase 3 — Business Operations (~4–5 weeks)

### Feature 6: Accounts Receivable & Payable

**Behaviour:**
- AR: tracks invoices sent to clients — amount, client, due date, status (open/paid/overdue)
- AP: tracks bills from vendors — amount, vendor, due date, status
- When an AR invoice is marked paid: auto-posts an Income transaction to the ledger (deduplication guard applies)
- When an AP bill is marked paid: auto-posts an Expense transaction to the ledger
- Dashboard shows: open AR total, overdue AR count, upcoming AP due this week

**Entry schema (`memory/ar_ap.json`):**
```json
{
  "receivables": [
    {
      "id": "uuid",
      "client": "Acme Corp",
      "amount": 3500.00,
      "issue_date": "2026-03-26",
      "due_date": "2026-04-25",
      "status": "overdue",
      "notes": "Invoice #INV-001"
    }
  ],
  "payables": []
}
```

**New file:** `skills/ar_ap_engine.py`
- `add_receivable(client, amount, due_date, notes) -> dict`
- `add_payable(vendor, amount, due_date, notes) -> dict`
- `mark_paid(entry_id, entry_type, paid_date) -> dict` — returns ledger row to auto-post
- `get_aging(entries) -> list[dict]` — adds `days_outstanding` and `age_bucket` (current/30/60/90)

**UI — Operations → AR / AP:**
- Two-column layout: Receivable (green header) / Payable (red header)
- Each row: client/vendor, amount, age badge, "Mark Paid" button
- Add new entry via form or chat

**New endpoints:**
- `GET /api/ar-ap`
- `POST /api/ar-ap` body `{type: "receivable"|"payable", client_vendor, amount, due_date, notes}`
- `PUT /api/ar-ap/{id}/mark-paid` body `{paid_date}`

---

### Feature 7: Tax Estimates & Deadlines

**Behaviour:**
- Tax engine reads YTD net income from the ledger (Income − Expenses)
- Computes: self-employment tax (15.3% of 92.35% of net income) + estimated federal income tax using 2026 brackets for single filer
- Shows estimated Q2/Q3/Q4 payment amounts and due dates
- IRS deadline calendar hardcoded for the current tax year + 30-day advance alerts
- Agent alerts the user in chat when a deadline is within 30 days (checked on status poll)

**New file:** `skills/tax_engine.py`
- `compute_se_tax(net_income: float) -> float` — 15.3% × 92.35%
- `compute_estimated_federal(net_income: float) -> float` — 2026 single-filer brackets
- `get_quarterly_estimate(net_income: float) -> dict` — `{se_tax, federal, total, due_date}`
- `get_irs_deadlines(year: int) -> list[dict]` — Q1–Q4 dates + annual return
- `get_upcoming_alerts(deadlines, days_ahead=30) -> list[dict]`

**UI — Operations → Tax:**
- Left: Q2 estimate breakdown (YTD income → SE tax + federal → total due + due date)
- Right: IRS deadline calendar with colour-coded badges (blue = upcoming, grey = future, red = overdue)

**New endpoints:**
- `GET /api/tax?year=YYYY`

---

## Data Architecture Summary

```
memory/
  long_term/{business_key}/
    config.json           (existing)
    category_rules.json   (new — Phase 1)
    recurring.json        (new — Phase 1)
    budgets.json          (new — Phase 2)
    ar_ap.json            (new — Phase 3)

skills/
  categorization_engine.py   (new — Phase 1)
  recurring_engine.py        (new — Phase 1)
  financial_statements.py    (new — Phase 2)
  budget_engine.py           (new — Phase 2)
  reconciliation_engine.py   (new — Phase 2)
  ar_ap_engine.py            (new — Phase 3)
  tax_engine.py              (new — Phase 3)

  google_sheets_manager.py   (existing — read-only for new features)
  document_processor.py      (existing — reused by reconciliation)
  payroll_engine.py          (existing — unchanged)
```

All new memory files live under `memory/long_term/{business_key}/` so data is isolated per business. `memory_manager.py` gets one load/save method pair per new file.

---

## What Does Not Change

- Google Sheet Ledger (`Ledger!A:G`) is the sole transaction store — no new transaction tables
- `memory/short_term.json`, `skill_memory.json`, `transaction_audit.json`, `learned_sources.json` — unchanged
- Existing API endpoints — unchanged and backwards compatible
- `main.py` agent reasoning loop — new skills wired in as additional action types, no restructuring
- `memory_manager.py` public interface — additive only

---

## Out of Scope

- Invoice PDF generation (Phase 3 tracks AR/AP but does not generate printable invoices)
- Multi-user / role-based access
- Email or SMS notifications (alerts are in-UI only)
- Mobile layout optimisation
- Payroll engine improvements (separate initiative)
