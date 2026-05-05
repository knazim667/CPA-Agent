"""
LLC Chart of Accounts and transaction classification engine.

Account numbering follows standard COA conventions:
  1000-1999  Assets
  2000-2999  Liabilities
  3000-3999  Equity
  4000-4999  Revenue
  5000-5999  COGS
  6000-8999  Expenses
  9000-9999  Tax accounts
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Account:
    number: int
    name: str
    normal_balance: str   # "debit" or "credit"
    category: str         # Assets / Liabilities / Equity / Revenue / COGS / Expenses
    ledger_type: str      # Income / Expense / Equity / Asset / Liability — maps to the Ledger Type column


# ── Full LLC Chart of Accounts ────────────────────────────────────────────────

ACCOUNTS: dict[int, Account] = {
    # --- Assets ---
    1010: Account(1010, "Checking Account",      "debit",  "Assets",      "Asset"),
    1020: Account(1020, "Savings Account",        "debit",  "Assets",      "Asset"),
    1030: Account(1030, "Petty Cash",             "debit",  "Assets",      "Asset"),
    1100: Account(1100, "Accounts Receivable",    "debit",  "Assets",      "Asset"),
    1200: Account(1200, "Inventory",              "debit",  "Assets",      "Asset"),
    1300: Account(1300, "Prepaid Expenses",       "debit",  "Assets",      "Asset"),
    1400: Account(1400, "Other Current Assets",   "debit",  "Assets",      "Asset"),
    1500: Account(1500, "Equipment",              "debit",  "Assets",      "Asset"),
    1510: Account(1510, "Accumulated Depreciation - Equipment", "credit", "Assets", "Asset"),
    1600: Account(1600, "Vehicles",               "debit",  "Assets",      "Asset"),
    1610: Account(1610, "Accumulated Depreciation - Vehicles",  "credit", "Assets", "Asset"),
    1700: Account(1700, "Office Furniture",       "debit",  "Assets",      "Asset"),
    1800: Account(1800, "Leasehold Improvements", "debit",  "Assets",      "Asset"),
    # --- Liabilities ---
    2000: Account(2000, "Accounts Payable",       "credit", "Liabilities", "Liability"),
    2100: Account(2100, "Credit Card Payable",    "credit", "Liabilities", "Liability"),
    2200: Account(2200, "Loans Payable",          "credit", "Liabilities", "Liability"),
    2210: Account(2210, "SBA Loan Payable",       "credit", "Liabilities", "Liability"),
    2300: Account(2300, "Sales Tax Payable",      "credit", "Liabilities", "Liability"),
    2400: Account(2400, "Payroll Liabilities",    "credit", "Liabilities", "Liability"),
    2500: Account(2500, "Deferred Revenue",       "credit", "Liabilities", "Liability"),
    2900: Account(2900, "Other Current Liabilities", "credit", "Liabilities", "Liability"),
    # --- Equity ---
    3000: Account(3000, "Owner's Capital",        "credit", "Equity",      "Equity"),
    3100: Account(3100, "Owner's Draws",          "debit",  "Equity",      "Equity"),  # contra-equity
    3200: Account(3200, "Retained Earnings",      "credit", "Equity",      "Equity"),
    3300: Account(3300, "Member Contributions",   "credit", "Equity",      "Equity"),  # multi-member LLC
    # --- Revenue ---
    4000: Account(4000, "Sales Revenue",          "credit", "Revenue",     "Income"),
    4100: Account(4100, "Service Revenue",        "credit", "Revenue",     "Income"),
    4200: Account(4200, "Consulting Revenue",     "credit", "Revenue",     "Income"),
    4300: Account(4300, "Rental Income",          "credit", "Revenue",     "Income"),
    4400: Account(4400, "Interest Income",        "credit", "Revenue",     "Income"),
    4500: Account(4500, "Other Income",           "credit", "Revenue",     "Income"),
    # --- COGS ---
    5000: Account(5000, "Cost of Goods Sold",     "debit",  "COGS",        "Expense"),
    5100: Account(5100, "Direct Labor",           "debit",  "COGS",        "Expense"),
    5200: Account(5200, "Materials & Supplies (COGS)", "debit", "COGS",    "Expense"),
    # --- Operating Expenses ---
    6000: Account(6000, "Advertising & Marketing","debit",  "Expenses",    "Expense"),
    6100: Account(6100, "Auto & Travel",          "debit",  "Expenses",    "Expense"),
    6200: Account(6200, "Bank & Merchant Fees",   "debit",  "Expenses",    "Expense"),
    6300: Account(6300, "Contract Labor",         "debit",  "Expenses",    "Expense"),
    6400: Account(6400, "Insurance",              "debit",  "Expenses",    "Expense"),
    6500: Account(6500, "Meals & Entertainment",  "debit",  "Expenses",    "Expense"),  # 50% deductible
    6600: Account(6600, "Office Supplies",        "debit",  "Expenses",    "Expense"),
    6700: Account(6700, "Professional Fees",      "debit",  "Expenses",    "Expense"),
    6800: Account(6800, "Rent & Lease",           "debit",  "Expenses",    "Expense"),
    6900: Account(6900, "Repairs & Maintenance",  "debit",  "Expenses",    "Expense"),
    7000: Account(7000, "Software & Subscriptions", "debit","Expenses",    "Expense"),
    7100: Account(7100, "Taxes & Licenses",       "debit",  "Expenses",    "Expense"),
    7200: Account(7200, "Utilities",              "debit",  "Expenses",    "Expense"),
    7300: Account(7300, "Wages & Salaries",       "debit",  "Expenses",    "Expense"),
    7400: Account(7400, "Depreciation Expense",   "debit",  "Expenses",    "Expense"),
    7500: Account(7500, "Amortization Expense",   "debit",  "Expenses",    "Expense"),
    7600: Account(7600, "Interest Expense",       "debit",  "Expenses",    "Expense"),
    7700: Account(7700, "Education & Training",   "debit",  "Expenses",    "Expense"),
    7800: Account(7800, "Shipping & Postage",     "debit",  "Expenses",    "Expense"),
    7900: Account(7900, "Other Operating Expenses", "debit","Expenses",    "Expense"),
    # --- Tax Accounts ---
    9100: Account(9100, "Income Tax Expense",     "debit",  "Expenses",    "Expense"),
    9200: Account(9200, "Self-Employment Tax",    "debit",  "Expenses",    "Expense"),
}

# Lookup by account name (lowercase) for reverse resolution
_BY_NAME: dict[str, Account] = {a.name.lower(): a for a in ACCOUNTS.values()}


def get_account(number: int) -> Account | None:
    return ACCOUNTS.get(number)


def get_account_by_name(name: str) -> Account | None:
    return _BY_NAME.get(name.strip().lower())


# ── Transaction Classification Rules ─────────────────────────────────────────
#
# Each rule is (keyword_list, account_number, entry_type, note).
# Checked in order; first match wins.  Entry type is the Ledger "Type" column
# value: "Income", "Expense", or "Equity".
#
# CRITICAL DISTINCTIONS:
#   owner capital / contribution → Equity, NOT Income
#   owner draw / withdrawal      → Equity, NOT Expense
#   loan received                → Liability, NOT Income
#   loan repayment               → Liability, NOT Expense
#   sale / service delivered     → Income
#   operating cost               → Expense

_CLASSIFICATION_RULES: list[tuple[list[str], int, str, str]] = [
    # ── Equity ────────────────────────────────────────────────────────────────
    (["owner capital", "capital contribution", "contributed capital",
      "add capital", "invest capital", "member contribution",
      "owner invest", "owner put in", "owner funded"],
     3000, "Equity", "Owner's Capital — not revenue"),

    (["owner draw", "owner's draw", "owners draw", "owner withdrawal",
      "personal withdrawal", "withdrew", "draw from business",
      "owner took", "owner paid self"],
     3100, "Equity", "Owner's Draw — not expense"),

    # ── Liabilities ───────────────────────────────────────────────────────────
    (["loan received", "borrowed", "bank loan", "sba loan", "line of credit",
      "loan proceeds", "took out loan", "financed"],
     2200, "Liability", "Loan received — not income"),

    (["loan payment", "loan repayment", "paid loan", "repaid loan",
      "principal payment", "debt payment"],
     2200, "Liability", "Loan repayment — not expense"),

    (["credit card payment", "paid credit card", "cc payment"],
     2100, "Liability", "Credit card payoff — not expense"),

    # ── Revenue / Income ──────────────────────────────────────────────────────
    (["invoice paid", "payment received", "client payment", "customer payment",
      "sales revenue", "service revenue", "consulting fee", "retainer"],
     4100, "Income", "Service/consulting revenue"),

    (["product sale", "sold", "merchandise", "retail sale"],
     4000, "Income", "Product sales revenue"),

    (["rental income", "rent received", "tenant payment"],
     4300, "Income", "Rental income"),

    (["interest earned", "interest income", "bank interest"],
     4400, "Income", "Interest income"),

    # ── COGS ──────────────────────────────────────────────────────────────────
    (["cost of goods", "cogs", "inventory purchased", "materials for job",
      "direct materials", "product cost"],
     5000, "Expense", "Cost of goods sold"),

    # ── Operating Expenses ────────────────────────────────────────────────────
    (["facebook ad", "google ad", "instagram ad", "marketing", "advertising",
      "promotion", "sponsored post"],
     6000, "Expense", "Advertising & Marketing"),

    (["mileage", "gas", "fuel", "parking", "toll", "airfare", "flight",
      "hotel", "uber", "lyft", "car rental", "auto expense"],
     6100, "Expense", "Auto & Travel"),

    (["bank fee", "wire fee", "stripe fee", "paypal fee", "merchant fee",
      "transaction fee", "nsf fee", "overdraft fee"],
     6200, "Expense", "Bank & Merchant Fees"),

    (["contractor", "freelancer", "subcontractor", "1099", "independent contractor"],
     6300, "Expense", "Contract Labor"),

    (["insurance", "liability insurance", "health insurance", "general liability"],
     6400, "Expense", "Insurance"),

    (["meal", "lunch", "dinner", "breakfast", "restaurant", "coffee", "food",
      "entertainment", "client dinner"],
     6500, "Expense", "Meals & Entertainment (50% deductible)"),

    (["office supply", "office supplies", "paper", "ink", "toner", "staples",
      "printer supplies", "pens", "notebooks"],
     6600, "Expense", "Office Supplies"),

    (["attorney", "lawyer", "legal fee", "cpa fee", "accountant fee",
      "professional fee", "consulting fee paid", "tax prep"],
     6700, "Expense", "Professional Fees"),

    (["rent", "lease payment", "office rent", "studio rent", "commercial rent"],
     6800, "Expense", "Rent & Lease"),

    (["repair", "maintenance", "fix", "cleaning", "janitorial", "plumbing",
      "hvac", "landscaping"],
     6900, "Expense", "Repairs & Maintenance"),

    (["software", "subscription", "saas", "app", "cloud service", "adobe",
      "microsoft 365", "quickbooks", "zoom", "slack", "notion"],
     7000, "Expense", "Software & Subscriptions"),

    (["business license", "license fee", "permit", "registration fee",
      "state tax", "local tax", "sales tax paid"],
     7100, "Expense", "Taxes & Licenses"),

    (["electric", "electricity", "water", "gas bill", "internet", "phone",
      "utility", "utilities"],
     7200, "Expense", "Utilities"),

    (["payroll", "salary", "wages", "employee pay", "w-2", "hourly"],
     7300, "Expense", "Wages & Salaries"),

    (["depreciation"],
     7400, "Expense", "Depreciation Expense"),

    (["interest expense", "loan interest", "mortgage interest"],
     7600, "Expense", "Interest Expense"),

    (["training", "course", "class", "certification", "education", "seminar",
      "conference", "workshop"],
     7700, "Expense", "Education & Training"),

    (["shipping", "postage", "fedex", "ups", "usps", "freight", "delivery"],
     7800, "Expense", "Shipping & Postage"),
]


def classify_transaction(description: str, amount: float = 0.0, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """
    Return the best-match account and entry type for a transaction description.

    Returns:
        {
          "account_number": int,
          "account_name": str,
          "category": str,           # COA category (Assets, Liabilities, Equity, Revenue, COGS, Expenses)
          "ledger_type": str,        # "Income", "Expense", or "Equity"
          "note": str,               # human-readable classification rationale
          "confidence": float,
        }
        or None if no rule matched.
    """
    desc = description.strip().lower()
    for keywords, acct_num, ledger_type, note in _CLASSIFICATION_RULES:
        for kw in keywords:
            if kw in desc:
                acct = ACCOUNTS[acct_num]
                return {
                    "account_number": acct_num,
                    "account_name": acct.name,
                    "category": acct.category,
                    "ledger_type": ledger_type,
                    "note": note,
                    "confidence": 0.90,
                }
    return None


def get_coa_summary() -> list[dict[str, Any]]:
    """Return all accounts as a list of dicts, sorted by account number."""
    return [
        {
            "number": a.number,
            "name": a.name,
            "category": a.category,
            "normal_balance": a.normal_balance,
            "ledger_type": a.ledger_type,
        }
        for a in sorted(ACCOUNTS.values(), key=lambda x: x.number)
    ]
