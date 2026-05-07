# CPA-Agent Accounting & Tax Training Plan

**Source document:** [Comprehensive Framework for AI-Driven Accounting Systems and Regulatory Tax Compliance](https://docs.google.com/document/d/1PU5nSY7C0nQPk_xQoQ_hz-wFreomQc35V88yJ0Z21Lw/edit)
**Created:** 2026-05-05
**Purpose:** Train CPA-Agent with professional-grade accounting and tax knowledge based on the reference document above.

---

## Current State (Already Done)

| Domain | File | Status |
|---|---|---|
| Double-entry rules + COA table | `persona/system_prompt.md` | Done |
| Chart of Accounts (56 accounts) | `skills/chart_of_accounts.py` | Done |
| Transaction classification (COA + keyword rules) | `skills/chart_of_accounts.py` + `skills/categorization_engine.py` | Done |
| Tax engine (SE tax, 2025 brackets, QBI, mileage, Section 179 limits) | `skills/tax_engine.py` | Done |
| AR/AP engine | `skills/ar_ap_engine.py` | Done |
| Payroll engine (basic gross pay, FICA) | `skills/payroll_engine.py` | Done — needs Phase 4 update |

---

## Phase 1 — System Prompt Additions ✅ COMPLETED 2026-05-05

**File updated:** `persona/system_prompt.md`
**Impact:** Immediate — agent gets smarter without any new code

Knowledge to add from the source document:

### 1.1 Accrual vs. Cash Basis Rules
- Revenue is recognized when **earned** (invoice issued / performance obligation met), NOT when cash is received
- Expenses are recognized when **incurred** (bill received), NOT when cash is paid
- Accounts Receivable (1100) = revenue earned but not yet collected
- Accounts Payable (2000) = expense incurred but not yet paid
- Prepaid Expenses (1300) = cash paid in advance for future periods — amortize monthly

### 1.2 Schedule M-1 Book-Tax Adjustments
These are differences between what appears on the P&L (books) and what is deductible on the tax return:
- **Meals & Entertainment**: 50% limitation — if $1,000 on books, only $500 deductible → flag $500 on M-1 Line 4
- **Fines & penalties**: 100% non-deductible on tax return, but recorded as expense on books
- **Tax-exempt interest income**: on books as income, not taxable on return
- **Officer life insurance premiums**: non-deductible if company is the beneficiary
- **Depreciation timing**: MACRS (tax) is accelerated vs. GAAP straight-line (book) → creates timing difference

### 1.3 Trust Fund Recovery Penalty
- Payroll taxes withheld from employees belong to the U.S. Treasury — NOT to the business
- IRS can hold owners personally liable even inside an LLC
- Agent must prioritize payroll tax deposits above all other vendor payments
- Deposit schedule: monthly (< $50,000 prior-year liability) or semi-weekly (≥ $50,000)
- All deposits via EFTPS (Electronic Federal Tax Payment System)

### 1.4 Inventory Method Rule
- On business setup, ask which inventory costing method: FIFO, LIFO, or Weighted Average (WAC)
- FIFO: oldest units sold first — higher profits in inflation, higher taxes
- LIFO: newest units sold first — lower profits in inflation, tax deferral (GAAP only, not IFRS)
- WAC: average cost per unit — smoothed results
- LIFO is not allowed under IFRS

### 1.5 Capital vs. Repair Decision Tree
- < $2,500: Expense immediately (IRS de minimis safe harbor)
- "Restores to original condition" (broken window, patch roof): Expense
- "Extends useful life OR adds new capability" (full roof replacement, new wing): Capitalize → depreciate
- Capitalize: DR 1500 Equipment / CR 1010 Checking
- Expense: DR 6900 Repairs & Maintenance / CR 1010 Checking

### 1.6 Section 1245 Recapture on Asset Sale
- When a depreciated asset is sold, any gain up to the amount of depreciation taken is taxed as **ordinary income** (not capital gain)
- Example: Machine bought for $10,000, depreciated to $4,000 adjusted basis, sold for $7,000 → $3,000 gain is ALL ordinary income (recaptured depreciation)
- Agent must flag this scenario and note that Form 4797 is required

### 1.7 Inter-Company Transaction Rules (Multi-Business LLC)
- Transactions between divisions/subsidiaries must be tagged with source and destination division
- Revenue on one side = expense on the other — both must be eliminated on consolidated statements
- Use "Due to [Division]" (liability) and "Due from [Division]" (asset) accounts
- All inter-company transactions need market-rate pricing (arm's-length) to satisfy IRS scrutiny

---

## Phase 2 — Depreciation Engine ✅ COMPLETED 2026-05-05

**File created:** `skills/depreciation_engine.py`
**Impact:** Agent can handle any asset purchase end-to-end

### What to build:

```python
class DepreciationEngine:
    # MACRS GDS recovery period tables
    RECOVERY_PERIODS = {
        "computer": 5,
        "vehicle": 5,
        "office_furniture": 7,
        "equipment": 7,
        "land_improvement": 15,
        "residential_rental": 27.5,
        "commercial_building": 39,
    }

    MACRS_200DB_RATES = {
        5: [0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576],   # 5-year, half-year convention
        7: [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],  # 7-year
    }

    SECTION_179_LIMIT_2025 = 1_250_000
    BONUS_DEPRECIATION_2025 = 0.40   # 40% first-year bonus (check IRS for current year)

    def compute_macrs_schedule(self, cost, asset_type, year_placed_in_service) -> list[dict]
    def apply_section_179(self, cost, elected_amount) -> dict
    def apply_bonus_depreciation(self, cost, after_179_basis, tax_year) -> dict
    def compute_disposal(self, original_cost, accumulated_depreciation, sale_proceeds) -> dict
        # Returns: gain_or_loss, recaptured_as_ordinary, capital_gain_portion
    def detect_mid_quarter_convention(self, assets_placed_in_service: list) -> bool
        # Returns True if >40% of annual asset basis was placed in service in Q4
```

### Key logic:
- Half-year convention: all property gets half a year of depreciation in year 1 and year N
- Mid-quarter convention triggers if >40% of assets placed in Q4
- 200% declining balance switches to straight-line when straight-line gives a larger deduction
- Section 179 is elected first, then bonus depreciation on remaining basis, then MACRS on what remains

---

## Phase 3 — Inventory Engine ✅ COMPLETED 2026-05-05

**File created:** `skills/inventory_engine.py`
**Prerequisite:** Business must sell physical products (ask on setup)

### What to build:

```python
class InventoryEngine:
    # Supported methods: "fifo", "lifo", "wac"

    def add_purchase(self, units, unit_cost, freight=0, duties=0, insurance=0) -> dict
        # Landed cost = (base + freight + duties + insurance) / units
        # DR 1200 Inventory / CR 1010 Checking (for full landed cost)

    def record_sale(self, units_sold, sale_price, method="fifo") -> dict
        # Returns COGS amount and the two journal entries:
        # 1. DR 1010 Cash / CR 4000 Sales Revenue
        # 2. DR 5000 COGS / CR 1200 Inventory

    def check_impairment(self, inventory_item, market_value) -> dict | None
        # Lower of cost or market (LCM) rule
        # If market_value < recorded_cost → write-down
        # DR Inventory Write-Down Expense / CR 1200 Inventory

    def get_inventory_value(self, method="fifo") -> float
    def get_cogs_for_period(self, method="fifo") -> float
```

### Key points:
- Landed cost = base price + freight + customs/duties + insurance + handling
- On sale, two entries are always needed (revenue entry + COGS entry)
- LIFO reserve: if switching from FIFO to LIFO, track the difference as a balance sheet reserve
- Perpetual method preferred (update inventory after every transaction)

---

## Phase 4 — Payroll Engine Update

**File to update:** `skills/payroll_engine.py`
**Estimated effort:** ~1 hour
**Impact:** Correct payroll withholding for pre-tax benefits

### What to update:

```python
def compute_net_pay(
    gross_pay: float,
    retirement_401k: float = 0,   # reduces federal income tax base AND FICA base? No — 401k only reduces FIT
    section_125_health: float = 0, # reduces BOTH federal income tax base AND FICA base
    filing_status: str = "single",
    allowances: int = 0,
) -> dict:
    # Step 1: Gross pay
    # Step 2: Deduct Section 125 (health/dental/vision) from BOTH FIT base and FICA base
    # Step 3: Deduct 401(k) from FIT base only (NOT from FICA base)
    # Step 4: Apply withholding tables (Publication 15-T) to FIT base
    # Step 5: Apply FICA to FICA base (6.2% SS up to $184,500 + 1.45% Medicare)
    # Step 6: Calculate employer match (same FICA + FUTA/SUTA)
    # Step 7: Net pay = Gross - FIT withholding - employee FICA - pre-tax deductions
```

### 2026 payroll constants to update:
- Social Security wage base: **$184,500** (from source document)
- Social Security rate: 6.2% (employee) + 6.2% (employer match)
- Medicare rate: 1.45% + 1.45% match, plus 0.9% additional Medicare for wages > $200,000 (employee only)
- FUTA: 6.0% on first $7,000 per employee (net 0.6% after state credit)

---

## Phase 5 — Schedule M-1 Reconciliation Tracker (Future / Year-End)

**File to create:** `skills/m1_reconciler.py`
**Estimated effort:** 2–3 hours
**When to build:** Before first tax season use

### What to build:
- Track book income vs. taxable income differences throughout the year
- Auto-flag meals at 50%
- Track GAAP depreciation vs. MACRS depreciation difference each year
- Identify non-deductible items (fines, officer life insurance if company is beneficiary)
- Generate a draft M-1 table the CPA can review:

```
Schedule M-1 Draft
==================
Line 1:  Net income per books:              $XX,XXX
Line 2:  Federal income tax (C-Corp only):  $X,XXX
Line 5a: Meals & entertainment (50% limit): $XXX
Line 5b: Depreciation timing difference:    $XXX
Line 7:  Other non-deductible expenses:     $XXX
Line 8:  Taxable income per return:         $XX,XXX
```

---

## Phase 6 — Transaction Splitting (Future)

**File to update:** `skills/categorization_engine.py` + `main.py`
**When to build:** When users start reporting split transactions (e.g., Amazon order with supplies + inventory + personal)

### What to build:
- `split_transaction(total_amount, splits: list[dict])` — takes one transaction and creates multiple ledger rows
- UI support: allow user to say "split this $200 Amazon charge: $100 office supplies, $100 inventory"
- Each split maps to its own COA account

---

## Execution Order

```
✅ Phase 1 (DONE)   → system_prompt.md — accrual, M-1, trust fund, inventory method, recapture, inter-company rules
✅ Phase 2 (DONE)   → skills/depreciation_engine.py — MACRS tables, 179, bonus, disposal recapture, mid-quarter
✅ Phase 3 (DONE)   → skills/inventory_engine.py — FIFO/LIFO/WAC, landed cost, LCM impairment, LIFO reserve
✅ Phase 4 (DONE)   → Update skills/payroll_engine.py — 401k/Section 125 pre-tax deductions, 2026 SS wage base
   Phase 3          → Build skills/inventory_engine.py (only if business sells physical goods)
   Phase 4          → Update skills/payroll_engine.py pre-tax deductions (401k, Section 125)
   Phase 5          → Build skills/m1_reconciler.py (before tax season)
   Phase 6          → Transaction splitting support
```

---

## Notes

- The source document mentions Merchant Category Codes (MCC) as a way to improve categorization. This requires a transaction data feed (bank API) that includes MCC metadata — not currently available in the system but worth noting for future integration.
- The document recommends a "trust but verify" workflow where the AI suggests categories with a visual marker and the user confirms. This is already partially implemented via the `suggest_category()` flow in `categorization_engine.py`.
- Consolidated financial statements with inter-company eliminations (Phase 1.7) only matter when the active business has multiple sub-divisions set up in the system.
