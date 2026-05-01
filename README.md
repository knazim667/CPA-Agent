# CPA-Agent

CPA-Agent is a local-first AI accounting assistant for small businesses. It combines an LLM reasoning layer with Google Sheets as a live ledger, a self-reflection safety pass on every action, and a full-featured browser UI — so you can manage your books, taxes, AR/AP, and cash flow entirely through a chat interface backed by a real spreadsheet.

## What It Does

You talk to the agent in plain language. It records transactions, tracks receivables and payables, estimates taxes, generates P&L and cash-flow statements, runs recurring billing, monitors your budget, and lets you reconcile against a bank statement — all stored in a Google Sheet you own.

---

## Features

### Core Agent
- **Multi-LLM support** — Ollama (local), OpenAI, Gemini, or OpenRouter
- **Dual-model pipeline** — a fast reasoning model writes the plan; a separate reflection model vetoes unsafe accounting actions
- **Business silos** — unlimited businesses, each with its own ledger sheet, doc, memory, and settings
- **Custom correction rules** — teach the agent your preference (e.g., always use "Office Rent" not "Rent") and it obeys forever
- **Learned knowledge** — feed it Google Sheets or Docs URLs and it internalizes the reference material for future prompts

### Transactions & Ledger
- Natural-language transaction recording to Google Sheets (single or bulk)
- Duplicate detection and one-command bulk deletion
- Automatic category suggestion from description text
- 7-column ledger: Date, Description, Category, Amount, Type, Reference, Notes
- Formatted Google Sheet with frozen header, currency columns, and auto-sized rows

### Financial Statements
- **P&L Summary** — income vs. expenses, net profit
- **Cash Flow Statement** — operating, investing, financing activities
- **Balance Sheet** — assets, liabilities, equity snapshot

### AR / AP Tracker
- Add receivables (money owed to you) and payables (bills you owe)
- Mark entries paid — auto-posts to ledger
- Overdue detection with days outstanding
- Dashboard cards for open receivables total, overdue count, and upcoming bills

### Tax Engine
- Quarterly self-employment tax estimate from ledger income
- Federal income tax bracket estimate
- IRS deadline calendar (Q1–Q4 estimated, annual return)
- 30-day upcoming deadline alerts shown in the dashboard

### Budget Engine
- Set a monthly spend cap per category
- Actual vs. budget comparison with variance reporting

### Recurring Transactions
- Schedule a repeating income or expense (e.g., monthly rent)
- Auto-posts when the scheduled date arrives (checked on every status poll)

### Reconciliation
- Upload a CSV bank statement
- Match against ledger rows automatically
- Review unmatched and matched items in-browser

### Document Management
- Upload invoices, receipts, PDFs, and images
- OCR text extraction (requires Tesseract)
- Notes appended to the active Google Doc

---

## Web UI Tabs

| Tab | What It Shows |
|-----|---------------|
| Dashboard | Key metrics, recent transactions, tax alerts, AR/AP cards |
| Chat | Conversational interface with markdown-rendered responses |
| Ledger | Paginated transaction table with search and date filter |
| AR / AP | Receivables and payables with status and days outstanding |
| Recurring | Active recurring schedules |
| Balance Sheet | Snapshot of assets, liabilities, equity |
| Cash Flow | Operating, investing, and financing cash flows |
| Budget | Monthly budget vs. actual by category |
| Reconcile | Bank statement upload and matching |
| Tax | Tax estimate, deadlines, and alerts |
| Documents | Upload and attach receipts or invoices |

---

## Quick Start

### 1 — Clone and install

```bash
git clone https://github.com/yourusername/CPA-Agent.git
cd CPA-Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2 — Choose a model provider

**Ollama (local, no API key needed)**

```bash
brew install ollama
ollama pull llama3.1:8b

export MODEL_PROVIDER="ollama"
export OLLAMA_MODEL="llama3.1:8b"
```

Recommended multi-model setup for better quality:

```bash
ollama pull llama3.3:70b
ollama pull deepseek-r1:32b

export OLLAMA_QUALITY_MODEL="llama3.3:70b"
export OLLAMA_REFLECTION_MODEL="deepseek-r1:32b"
export CPA_AGENT_REASONING_MODE="fast"
```

**OpenAI**

```bash
export MODEL_PROVIDER="openai"
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

**Gemini**

```bash
export MODEL_PROVIDER="gemini"
export GEMINI_API_KEY="..."
export GEMINI_MODEL="gemini-2.5-flash"
```

**OpenRouter** (access many models via one API key)

```bash
export MODEL_PROVIDER="openrouter"
export OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_MODEL="nvidia/llama-3.1-nemotron-ultra-253b-v1:free"
```

### 3 — Connect Google Workspace

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project, enable **Sheets API**, **Drive API**, and **Docs API**
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app**
4. Download the JSON file

```bash
export GOOGLE_OAUTH_CLIENT_SECRET_FILE="/path/to/your-oauth-client.json"
python3 authorize_google_oauth.py   # opens browser once, saves token
```

### 4 — Bootstrap your first business (optional)

```bash
python3 bootstrap_google_workspace.py
```

This creates a Google Sheet and Doc for each business defined in `memory/long_term/`, writes the IDs back to their config, and sets up the workbook with Ledger, P&L Summary, and Dashboard tabs.

### 5 — Start the app

```bash
python3 web_app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Example Chat Commands

```
Record $450 expense for AWS hosting
Add $2,500 income from Acme Corp consulting invoice
Add receivable $1,200 from ClientX due in 30 days
Add payable $800 for vendor AWS
Set marketing budget $500 per month
Schedule Rent $1,800 expense on the 1st every month
Show my tax estimate
Delete duplicates
Switch to Nazam LLC
```

---

## Project Structure

```
CPA-Agent/
├── core/
│   ├── google_auth.py          # OAuth2 + service account auth
│   ├── model_client.py         # Provider-agnostic LLM interface
│   ├── ollama_client.py
│   ├── openai_client.py
│   ├── gemini_client.py
│   └── openrouter_client.py
├── skills/
│   ├── google_sheets_manager.py   # Full Sheets CRUD, formatting, duplicate removal
│   ├── google_docs_manager.py     # Docs create + append
│   ├── ar_ap_engine.py            # Receivables and payables tracker
│   ├── budget_engine.py           # Monthly budget vs. actual
│   ├── categorization_engine.py   # Auto-suggest transaction category
│   ├── document_processor.py      # PDF/image OCR pipeline
│   ├── financial_statements.py    # P&L, cash flow, balance sheet
│   ├── knowledge_manager.py       # URL-fed reference memory
│   ├── payroll_engine.py          # Payroll template
│   ├── reconciliation_engine.py   # Bank statement matching
│   ├── recurring_engine.py        # Recurring transaction scheduler
│   └── tax_engine.py              # SE tax, federal estimate, deadlines
├── memory/
│   ├── long_term/
│   │   ├── Business_A/config.json
│   │   └── Business_B/config.json
│   └── transaction_audit.json
├── persona/
│   ├── system_prompt.md
│   └── custom_rules.json
├── ui/
│   ├── index.html
│   └── app.js
├── tests/
├── main.py                    # Agent core: reasoning, reflection, command routing
├── memory_manager.py          # Business silo and conversation memory
├── web_app.py                 # FastAPI server + REST endpoints
├── bootstrap_google_workspace.py
├── authorize_google_oauth.py
└── requirements.txt
```

---

## Architecture

```
User (chat / voice)
        │
        ▼
  web_app.py  ──── FastAPI REST API ────►  ui/index.html
        │
        ▼
  main.py  (CPAAgent)
   ├── detect_* shortcuts  (recurring, budget, AR/AP, tax, delete-dupes…)
   │       └── fast-path, no LLM call
   ├── run_reasoning()     → LLM call (reasoning model)
   ├── execute_action()    → skills dispatch (sheets, docs, AR/AP…)
   └── self_reflect()      → LLM call (reflection model, safety verifier)
        │
        ▼
  memory_manager.py   (business silos, conversation, budgets, recurring)
        │
        ▼
  skills/             (Google Sheets, Docs, AR/AP, Tax, Reconcile…)
        │
        ▼
  Google Workspace    (Sheets / Docs in your Google account)
```

Every LLM-generated action goes through a second model call that checks for math errors, cross-business leakage, and unsupported tax claims before the result is stored or shown.

---

## Environment Variables Reference

| Variable | Purpose | Default |
|----------|---------|---------|
| `MODEL_PROVIDER` | `ollama` / `openai` / `gemini` / `openrouter` | `ollama` |
| `OLLAMA_MODEL` | Default fast model | `llama3.1:8b` |
| `OLLAMA_QUALITY_MODEL` | High-quality reasoning model | same as above |
| `OLLAMA_REFLECTION_MODEL` | Safety verifier model | same as above |
| `CPA_AGENT_REASONING_MODE` | `fast` or `quality` | `fast` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `GEMINI_API_KEY` | Gemini API key | — |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.5-flash` |
| `OPENROUTER_API_KEY` | OpenRouter API key | — |
| `OPENROUTER_MODEL` | OpenRouter model name | — |
| `GOOGLE_OAUTH_CLIENT_SECRET_FILE` | Path to Desktop OAuth JSON | — |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to service-account JSON (alternative) | — |

---

## System Requirements

- Python 3.11+
- macOS (tested) / Linux
- `portaudio` for microphone input: `brew install portaudio`
- `tesseract` for receipt OCR: `brew install tesseract`

---

## Disclaimer

CPA-Agent is a productivity tool, not a licensed tax or accounting service. Tax estimates are approximations based on simple bracket math. Always have a licensed CPA review filings, payroll, and tax positions before submission.
