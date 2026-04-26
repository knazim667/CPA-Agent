# CPA-Agent Upgrade Design

**Date:** 2026-04-26
**Approach:** Backend-complete first, then full UI redesign (Approach 2)
**Scope:** OpenRouter integration, backend bug fixes, new reporting endpoints, clean modern UI

---

## 1. Goals

1. Add OpenRouter as a fourth model provider (free model: `nvidia/nemotron-3-super-120b-a12b:free`)
2. Fix all known backend bugs and stub integrations
3. Add P&L reporting, CSV export, and paginated ledger endpoints
4. Redesign the UI with a clean modern light theme and tabbed navigation

---

## 2. What We Are NOT Doing

- No database migration — data stays in Google Sheets + JSON files
- No user authentication — localhost-only, single user
- No recurring transactions (deferred)
- No balance sheet (requires chart of accounts, out of scope)
- No multi-currency UI (field exists in profile but no conversion logic)

---

## 3. Backend Phase

### 3.1 OpenRouter Client

**New file:** `core/openrouter_client.py`

OpenRouter exposes an OpenAI-compatible REST API at `https://openrouter.ai/api/v1`. The client:
- Sends `Authorization: Bearer <OPENROUTER_API_KEY>`
- Sends required headers: `HTTP-Referer: http://localhost:8000`, `X-Title: CPA-Agent`
- Uses `OPENROUTER_MODEL` env var (default: `nvidia/nemotron-3-super-120b-a12b:free`)
- Follows the same `chat(messages) -> str` interface as all other clients

**`core/model_client.py` changes:**
- Add `openrouter` branch to `get_model_client()`
- Both `purpose="reasoning"` and `purpose="reflection"` map to the same OpenRouter client (single model tier for free-tier usage)

**New env vars:**
```
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
```

### 3.2 Bug Fixes

#### Memory leak — `pending_document_drafts`
**File:** `web_app.py`
**Problem:** Dict grows unboundedly; drafts are never evicted if user does not approve.
**Fix:** Store `created_at` timestamp with each draft. At the start of every request that touches the dict, evict entries older than 3600 seconds. Cap total entries at 100 (drop oldest on overflow).

#### Brittle date inference — `_infer_dates_from_text`
**File:** `main.py`
**Problem:** `execute_action` contains a hardcoded list of product keywords (`"nozzle"`, `"filament"`, `"caliper"`, etc.) used to match descriptions to dates. This breaks for any business not selling 3D-printing supplies.
**Fix:** Replace the hardcoded keyword lists with a generic approach:
- Extract all `label: $amount` pairs from the input
- Extract all `MM/DD/YYYY` dates
- If there is exactly one date, use it for all rows
- If there are multiple dates, attempt to match by proximity (the nearest preceding date to each line wins)
- Remove all hardcoded product-name constants

#### Ledger row limit
**File:** `main.py` → `get_dashboard_snapshot()`
**Problem:** `read_range("Ledger!A1:G50")` silently truncates ledgers larger than 49 rows.
**Fix:** Change to `Ledger!A1:G` — Google Sheets API returns all data up to the last non-empty row with an open-ended range.

#### Payroll stub not integrated
**File:** `skills/payroll_engine.py`, `main.py`
**Problem:** `calculate_simple_payroll` exists but is never reachable via LLM tool calls.
**Fix:**
- Add `calculate_payroll` as a recognized action in `execute_action()`
- Parameters: `gross_pay` (float), `federal_rate` (float, optional, default 0.12)
- Returns structured result with `gross_pay`, `federal_withholding`, `social_security`, `medicare`, `net_pay`
- Also add the payroll result as a transaction row in the ledger (net pay as expense, optional)

#### Tax researcher stub not integrated
**File:** `skills/tax_researcher.py`, `main.py`
**Problem:** `fetch_tax_update` exists but is never reachable.
**Fix:**
- Add `research_tax` as a recognized action in `execute_action()`
- Parameters: `url` (str)
- Returns `title`, `summary` from the fetched page
- Stores the result in learned sources via `memory.record_learned_source()`

### 3.3 New Endpoints

#### `GET /api/report/pl`
Query params: `from_date` (YYYY-MM-DD, optional), `to_date` (YYYY-MM-DD, optional)

Logic:
1. Read all rows from `Ledger!A1:G` for the active business
2. Filter rows by date range if params are provided
3. Group income rows by category → sum amounts
4. Group expense rows by category → sum amounts
5. Compute `net = income_total - expense_total`

Response:
```json
{
  "business": "Business A",
  "from_date": "2026-01-01",
  "to_date": "2026-04-26",
  "income_by_category": [{"category": "Sales", "total": 5000.00}],
  "expense_by_category": [{"category": "Office Supplies", "total": 200.00}],
  "income_total": 5000.00,
  "expense_total": 200.00,
  "net": 4800.00
}
```

#### `GET /api/export/csv`
Query params: `from_date` (optional), `to_date` (optional)

Logic:
1. Read all ledger rows (same as P&L)
2. Filter by date range if provided
3. Return `StreamingResponse` with `Content-Type: text/csv` and `Content-Disposition: attachment; filename="<business_key>-ledger-<today>.csv"`
4. CSV columns: Date, Description, Category, Amount, Type, Reference, Notes

#### `GET /api/ledger`
Query params: `page` (int, default 1), `page_size` (int, default 20, max 100), `search` (str, optional), `from_date` (optional), `to_date` (optional)

Logic:
1. Read all ledger rows
2. Filter by date range
3. Filter rows where `search` appears in description or category (case-insensitive)
4. Paginate results
5. Return rows + `total_count`, `page`, `page_size`, `total_pages`

---

## 4. Frontend Phase

### 4.1 Design Tokens

```css
--bg: #F8FAFC;
--panel: #FFFFFF;
--border: #E2E8F0;
--text: #0F172A;
--muted: #64748B;
--accent: #2563EB;
--accent-hover: #1D4ED8;
--success: #16A34A;
--danger: #DC2626;
--warning-bg: #FFFBEB;
--shadow-sm: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
--shadow-md: 0 4px 16px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
--radius: 12px;
--radius-sm: 8px;
--font: 'Inter', system-ui, -apple-system, sans-serif;
```

### 4.2 Layout: Top Bar + Tabs

Replaces the fixed two-column sidebar layout.

```
┌─────────────────────────────────────────────────────────────┐
│  CPA-Agent   [▼ Business A]   [OPENROUTER • nemotron-120b]  │  top bar
├─────────────────────────────────────────────────────────────┤
│  Dashboard │ Ledger │ Reports │ Documents │ Chat            │  tabs
├─────────────────────────────────────────────────────────────┤
│                     active tab content                      │
└─────────────────────────────────────────────────────────────┘
```

**Top bar** (full-width, `#FFFFFF`, bottom border `1px solid var(--border)`):
- Left: logo + wordmark
- Center: business selector dropdown (inline, no separate button — changing selection auto-switches)
- Right: model badge (provider + model name) + settings gear (opens a slide-over for model mode and workspace links)

**Tab bar** (sticky below top bar):
- 5 tabs: Dashboard, Ledger, Reports, Documents, Chat
- Active tab: `border-bottom: 2px solid var(--accent)`, text `var(--accent)`
- Inactive: `var(--muted)`

### 4.3 Tab Content

#### Dashboard Tab
- 5 metric cards in a row: Transactions, Income, Expenses, Net Profit (color-coded ±), Flagged
- Net Profit card formula: `income - expenses`; positive → `var(--success)`, negative → `var(--danger)`
- Recent transactions list (5 rows)
- Write audit list (5 entries)

#### Ledger Tab
- Search input + date-range from/to pickers in a filter bar
- "Post Transaction" button → opens an inline slide-down form panel (same fields as current form)
- Paginated table: 20 rows/page, previous/next controls
- Calls `GET /api/ledger` with current filters

#### Reports Tab
- Date-range picker (from / to), "Generate Report" button
- After generation: two side-by-side tables — Income by Category, Expenses by Category
- Net Profit/Loss row at the bottom, styled green or red
- "Export CSV" button → triggers `GET /api/export/csv` download

#### Documents Tab
- Upload form (file input + instruction textarea + submit)
- Document draft cards: shows extracted table, total, approve button
- After approval: success toast, card collapses

#### Chat Tab
- Full chat log (all messages)
- Voice input button + voice reply toggle in tab header
- Message composer (textarea + Send button)
- `Cmd+Enter` / `Ctrl+Enter` keyboard shortcut to submit

### 4.4 New UX Components

#### Toast Notifications
- Position: top-right, `position: fixed`, z-index above everything
- Auto-dismiss after 4000ms with a fade-out animation
- Success (green left border), error (red left border), info (blue left border)
- Replaces all in-place status text (`transactionStatus`, `documentStatus`, etc.)

#### Loading Skeletons
- Shimmer animation (`background: linear-gradient(90deg, #F1F5F9 25%, #E2E8F0 50%, #F1F5F9 75%)`)
- Used in: metric cards during initial load, ledger table rows, recent transaction list

#### Settings Slide-Over
- Opens from the gear icon in the top bar
- Contains: model mode selector (Fast / Quality / OpenRouter), workspace links (Sheet, Doc), learned sources count
- Closes on backdrop click or Escape key

### 4.5 Files Changed

| File | Change type |
|---|---|
| `ui/index.html` | Full rewrite — tabbed layout, new component structure |
| `ui/styles.css` | Full rewrite — new design tokens, tab styles, skeleton, toast |
| `ui/app.js` | Full rewrite — tab router, P&L fetch, CSV export, toast system, skeleton states, settings slide-over |

---

## 5. Execution Order

1. `core/openrouter_client.py` — new file
2. `core/model_client.py` — add openrouter branch
3. `main.py` — fix date inference, fix row limit, wire payroll + tax actions
4. `web_app.py` — fix memory leak, add `/api/report/pl`, `/api/export/csv`, `/api/ledger`
5. `skills/__init__.py` — no export changes needed (payroll/tax accessed directly in main.py)
6. `ui/index.html` — full rewrite
7. `ui/styles.css` — full rewrite
8. `ui/app.js` — full rewrite

---

## 6. Acceptance Criteria

- [ ] `MODEL_PROVIDER=openrouter` routes all LLM calls through `https://openrouter.ai/api/v1`
- [ ] Setting `OPENROUTER_MODEL` to any model ID is respected
- [ ] `pending_document_drafts` entries older than 1 hour are evicted automatically
- [ ] Date inference works without any hardcoded product keywords
- [ ] Ledger read is not capped at 50 rows
- [ ] `/api/report/pl` returns correct category groupings and net figure
- [ ] `/api/export/csv` downloads a valid CSV with all ledger rows
- [ ] `/api/ledger` paginates correctly and filters by search + date range
- [ ] UI loads with tabbed layout on `http://127.0.0.1:8000`
- [ ] Net Profit metric card shows correct sign and color
- [ ] Toast appears on transaction success and error
- [ ] `Cmd+Enter` submits chat in Chat tab
- [ ] All existing features (voice, document upload, business switching) work in the new layout
