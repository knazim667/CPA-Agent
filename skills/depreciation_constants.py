"""MACRS IRS constants, rate tables, dataclass, and helper functions for DepreciationEngine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── IRS Constants ─────────────────────────────────────────────────────────────

SECTION_179_LIMITS: dict[int, int] = {
    2024: 1_220_000,
    2025: 1_250_000,
    2026: 1_250_000,
}

BONUS_DEPRECIATION_RATES: dict[int, float] = {
    2022: 1.00,
    2023: 0.80,
    2024: 0.60,
    2025: 0.40,
    2026: 0.20,
    2027: 0.00,
}

RECOVERY_PERIODS: dict[str, float] = {
    "computer":             5.0,
    "vehicle":              5.0,
    "office_furniture":     7.0,
    "equipment":            7.0,
    "land_improvement":    15.0,
    "residential_rental":  27.5,
    "commercial_building": 39.0,
}

MACRS_HALF_YEAR: dict[float, list[float]] = {
    5.0: [0.2000, 0.3200, 0.1920, 0.1152, 0.1152, 0.0576],
    7.0: [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
    15.0: [
        0.0500, 0.0950, 0.0855, 0.0770, 0.0693, 0.0623, 0.0590, 0.0590,
        0.0591, 0.0590, 0.0590, 0.0591, 0.0590, 0.0590, 0.0591, 0.0295,
    ],
}

SL_ANNUAL_RATE: dict[float, float] = {
    27.5: 1 / 27.5,
    39.0: 1 / 39.0,
}

SL_YEARS: dict[float, int] = {
    27.5: 28,
    39.0: 40,
}


@dataclass
class DepreciationYear:
    year_number: int
    deduction: float
    remaining_basis: float


# ── Private helpers used by DepreciationEngine ────────────────────────────────

def apply_rates(cost: float, rates: list[float], base_year: int) -> list[dict[str, Any]]:
    schedule = []
    remaining = cost
    for i, rate in enumerate(rates):
        deduction = min(round(cost * rate, 2), remaining)
        remaining = round(remaining - deduction, 2)
        schedule.append({
            "year_number": i + 1,
            "tax_year": base_year + i,
            "deduction": deduction,
            "remaining_basis": remaining,
        })
    return schedule


def compute_sl_schedule(
    cost: float, recovery_years: float, base_year: int, month_placed: int
) -> list[dict[str, Any]]:
    annual_rate = SL_ANNUAL_RATE[recovery_years]
    full_year_deduction = round(cost * annual_rate, 2)
    first_year_fraction = (12 - month_placed + 0.5) / 12
    first_deduction = round(cost * annual_rate * first_year_fraction, 2)
    total_years = SL_YEARS[recovery_years]
    schedule = []
    remaining = cost
    for i in range(total_years):
        if i == 0:
            d = first_deduction
        elif i == total_years - 1:
            d = remaining
        else:
            d = min(full_year_deduction, remaining)
        d = round(min(d, remaining), 2)
        remaining = round(remaining - d, 2)
        schedule.append({
            "year_number": i + 1,
            "tax_year": base_year + i,
            "deduction": d,
            "remaining_basis": remaining,
        })
        if remaining <= 0:
            break
    return schedule


def mid_quarter_rates(recovery_years: float, quarter: int) -> list[float]:
    _MQ_5YR: dict[int, list[float]] = {
        1: [0.35, 0.26, 0.156, 0.1116, 0.1116, 0.0558],
        2: [0.25, 0.30, 0.18, 0.1080, 0.1080, 0.0540],
        3: [0.15, 0.34, 0.204, 0.1224, 0.1224, 0.0612],
        4: [0.05, 0.38, 0.228, 0.1368, 0.1368, 0.0684],
    }
    _MQ_7YR: dict[int, list[float]] = {
        1: [0.25, 0.2143, 0.1531, 0.1093, 0.0875, 0.0875, 0.0875, 0.0459],
        2: [0.1786, 0.2347, 0.1676, 0.1197, 0.0940, 0.0940, 0.0940, 0.0174],
        3: [0.1071, 0.2552, 0.1823, 0.1302, 0.0929, 0.0892, 0.0893, 0.0538],
        4: [0.0357, 0.2755, 0.1969, 0.1406, 0.1004, 0.0893, 0.0893, 0.0723],
    }
    if recovery_years == 5.0:
        return _MQ_5YR.get(quarter, MACRS_HALF_YEAR[5.0])
    if recovery_years == 7.0:
        return _MQ_7YR.get(quarter, MACRS_HALF_YEAR[7.0])
    return list(MACRS_HALF_YEAR.get(recovery_years, []))


def disposal_journal_entries(
    original_cost: float, accum_dep: float, proceeds: float, gain_loss: float,
) -> list[dict[str, Any]]:
    entries = [
        {"debit":  {"account": 1010, "name": "Checking Account",       "amount": round(proceeds, 2)}},
        {"debit":  {"account": 1510, "name": "Accumulated Depreciation", "amount": round(accum_dep, 2)}},
        {"credit": {"account": 1500, "name": "Equipment (Asset)",       "amount": round(original_cost, 2)}},
    ]
    if gain_loss > 0:
        entries.append({"credit": {"account": 4500, "name": "Gain on Asset Sale (Other Income)", "amount": round(gain_loss, 2)}})
    elif gain_loss < 0:
        entries.append({"debit": {"account": 7900, "name": "Loss on Asset Disposal (Other Expense)", "amount": round(abs(gain_loss), 2)}})
    return entries


def disposal_tax_note(is_loss: bool, recaptured: float, sec_1231: float) -> str:
    if is_loss:
        return "Section 1231 loss — fully deductible as ordinary loss on Form 4797."
    parts = []
    if recaptured > 0:
        parts.append(f"${recaptured:,.2f} ordinary income (Section 1245 recapture)")
    if sec_1231 > 0:
        parts.append(f"${sec_1231:,.2f} Section 1231 gain (long-term capital gain if >1-year holding)")
    return "Form 4797 required. " + "; ".join(parts) + "."
