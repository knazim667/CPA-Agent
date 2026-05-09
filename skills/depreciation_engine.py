"""
MACRS depreciation engine for LLC assets.

Computes annual depreciation schedules, Section 179 elections, bonus depreciation,
mid-quarter convention detection, and Section 1245/1250 recapture on disposal.

Election order (IRS-prescribed):
  1. Section 179 first (elected expensing up to the annual limit)
  2. Bonus depreciation on remaining basis (percentage varies by tax year)
  3. MACRS on whatever basis remains after 179 and bonus
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ── IRS Constants ─────────────────────────────────────────────────────────────

SECTION_179_LIMITS: dict[int, int] = {
    2024: 1_220_000,
    2025: 1_250_000,
    2026: 1_250_000,   # placeholder — update when IRS publishes Rev. Proc.
}

# First-year bonus depreciation percentages by tax year
BONUS_DEPRECIATION_RATES: dict[int, float] = {
    2022: 1.00,
    2023: 0.80,
    2024: 0.60,
    2025: 0.40,
    2026: 0.20,
    2027: 0.00,
}

# ── MACRS GDS Recovery Period Table ─────────────────────────────────────────

RECOVERY_PERIODS: dict[str, float] = {
    "computer":              5.0,
    "vehicle":               5.0,
    "office_furniture":      7.0,
    "equipment":             7.0,
    "land_improvement":     15.0,
    "residential_rental":   27.5,
    "commercial_building":  39.0,
}

# ── Pre-computed MACRS Rate Tables (half-year convention) ─────────────────────
#
# 5-year and 7-year: 200% DB switching to SL (IRS Rev. Proc. 87-57, Table A-1)
# 15-year: 150% DB switching to SL (IRS Rev. Proc. 87-57, Table A-1)
# 27.5-year and 39-year: straight-line, approximated as uniform annual rate
# (Month-of-placement mid-month convention handled via first-year fraction)

_MACRS_HALF_YEAR: dict[float, list[float]] = {
    5.0: [0.2000, 0.3200, 0.1920, 0.1152, 0.1152, 0.0576],
    7.0: [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
    15.0: [
        0.0500, 0.0950, 0.0855, 0.0770, 0.0693, 0.0623, 0.0590, 0.0590,
        0.0591, 0.0590, 0.0590, 0.0591, 0.0590, 0.0590, 0.0591, 0.0295,
    ],
}

# Straight-line rates for real property (full-year; first year uses mid-month fraction)
_SL_ANNUAL_RATE: dict[float, float] = {
    27.5: 1 / 27.5,   # ≈ 3.636%
    39.0: 1 / 39.0,   # ≈ 2.564%
}

# Straight-line recovery years (real property depreciates one extra year due to partial first/last)
_SL_YEARS: dict[float, int] = {
    27.5: 28,
    39.0: 40,
}


@dataclass
class DepreciationYear:
    year_number: int          # 1 = first year asset in service
    deduction: float          # depreciation deduction for this year
    remaining_basis: float    # book/tax basis going into the next year


class DepreciationEngine:
    """Compute MACRS depreciation, Section 179, bonus depreciation, and asset disposal."""

    def compute_macrs_schedule(
        self,
        cost: float,
        asset_type: str,
        year_placed_in_service: int,
        month_placed_in_service: int = 7,
        mid_quarter_convention: bool = False,
        mid_quarter_quarter: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return the full year-by-year MACRS deduction schedule for an asset.

        Args:
            cost: depreciable basis (after any Section 179 / bonus elections)
            asset_type: key from RECOVERY_PERIODS
            year_placed_in_service: calendar year (e.g. 2025)
            month_placed_in_service: 1–12; used for SL real property mid-month convention
            mid_quarter_convention: True → use mid-quarter rates instead of half-year
            mid_quarter_quarter: 1–4; required when mid_quarter_convention is True

        Returns:
            list of dicts: [{year_number, tax_year, deduction, remaining_basis}, ...]
        """
        recovery = RECOVERY_PERIODS.get(asset_type)
        if recovery is None:
            raise ValueError(
                f"Unknown asset type '{asset_type}'. "
                f"Valid types: {list(RECOVERY_PERIODS.keys())}"
            )

        if recovery in _MACRS_HALF_YEAR:
            rates = list(_MACRS_HALF_YEAR[recovery])
            if mid_quarter_convention and mid_quarter_quarter in (1, 2, 3, 4):
                rates = _mid_quarter_rates(recovery, mid_quarter_quarter)
            return _apply_rates(cost, rates, year_placed_in_service)

        # Straight-line real property — mid-month convention
        return _compute_sl_schedule(
            cost, recovery, year_placed_in_service, month_placed_in_service
        )

    def apply_section_179(
        self, cost: float, elected_amount: float, tax_year: int = 2025
    ) -> dict[str, Any]:
        """
        Apply a Section 179 first-year expensing election.

        The elected amount cannot exceed the asset cost or the annual 179 limit.
        Returns the expensed amount and remaining depreciable basis.
        """
        limit = SECTION_179_LIMITS.get(tax_year, SECTION_179_LIMITS[2025])
        elected = min(elected_amount, cost, limit)
        remaining_basis = cost - elected
        return {
            "cost": round(cost, 2),
            "section_179_elected": round(elected, 2),
            "remaining_basis": round(remaining_basis, 2),
            "limit_applied": limit,
            "journal_entry": {
                "debit": {"account": 7400, "name": "Depreciation Expense", "amount": round(elected, 2)},
                "credit": {"account": 1510, "name": "Accumulated Depreciation", "amount": round(elected, 2)},
            },
        }

    def apply_bonus_depreciation(
        self, cost: float, after_179_basis: float, tax_year: int = 2025
    ) -> dict[str, Any]:
        """
        Apply bonus (first-year) depreciation to the basis remaining after 179.

        Args:
            cost: original asset cost (for reference)
            after_179_basis: depreciable basis after 179 election (may equal cost if no 179)
            tax_year: determines the bonus percentage (40% in 2025, 20% in 2026, 0% in 2027+)
        """
        rate = BONUS_DEPRECIATION_RATES.get(tax_year, 0.0)
        bonus_amount = after_179_basis * rate
        remaining_basis = after_179_basis - bonus_amount
        return {
            "original_cost": round(cost, 2),
            "after_179_basis": round(after_179_basis, 2),
            "bonus_rate": rate,
            "bonus_depreciation": round(bonus_amount, 2),
            "remaining_basis_for_macrs": round(remaining_basis, 2),
            "tax_year": tax_year,
            "journal_entry": {
                "debit": {"account": 7400, "name": "Depreciation Expense", "amount": round(bonus_amount, 2)},
                "credit": {"account": 1510, "name": "Accumulated Depreciation", "amount": round(bonus_amount, 2)},
            },
        }

    def compute_disposal(
        self,
        original_cost: float,
        accumulated_depreciation: float,
        sale_proceeds: float,
    ) -> dict[str, Any]:
        """
        Compute gain/loss on asset disposal and split between ordinary income and capital gain.

        Section 1245 recapture rule: gain up to total depreciation taken is ordinary income
        (not capital gain). Anything above that is Section 1231 gain (long-term capital gain
        treatment if holding period > 1 year).

        Returns:
            adjusted_basis, total_gain_loss, recaptured_as_ordinary_income,
            section_1231_gain, is_loss, requires_form_4797, journal_entries
        """
        adjusted_basis = original_cost - accumulated_depreciation
        total_gain_loss = sale_proceeds - adjusted_basis
        is_loss = total_gain_loss < 0

        if is_loss:
            recaptured_ordinary = 0.0
            section_1231_gain = 0.0
        else:
            # Recapture = lesser of: gain OR total depreciation taken
            recaptured_ordinary = min(total_gain_loss, accumulated_depreciation)
            section_1231_gain = total_gain_loss - recaptured_ordinary

        journal_entries = _disposal_journal_entries(
            original_cost, accumulated_depreciation, sale_proceeds, total_gain_loss
        )

        return {
            "original_cost": round(original_cost, 2),
            "accumulated_depreciation": round(accumulated_depreciation, 2),
            "adjusted_basis": round(adjusted_basis, 2),
            "sale_proceeds": round(sale_proceeds, 2),
            "total_gain_loss": round(total_gain_loss, 2),
            "recaptured_as_ordinary_income": round(recaptured_ordinary, 2),
            "section_1231_gain": round(section_1231_gain, 2),
            "is_loss": is_loss,
            "requires_form_4797": True,
            "tax_note": _disposal_tax_note(is_loss, recaptured_ordinary, section_1231_gain),
            "journal_entries": journal_entries,
        }

    def detect_mid_quarter_convention(
        self, assets_placed_in_service: list[dict[str, Any]]
    ) -> bool:
        """
        Return True if the mid-quarter convention applies for the year.

        The mid-quarter convention applies when more than 40% of the aggregate depreciable
        basis of personal property placed in service during the year was placed in service
        during the last 3 months (Q4) of the tax year.

        Each item in assets_placed_in_service must have:
            {"cost": float, "quarter": int}   # quarter: 1, 2, 3, or 4
        """
        if not assets_placed_in_service:
            return False

        total_basis = sum(float(a["cost"]) for a in assets_placed_in_service)
        if total_basis == 0:
            return False

        q4_basis = sum(
            float(a["cost"]) for a in assets_placed_in_service if int(a["quarter"]) == 4
        )
        return (q4_basis / total_basis) > 0.40

    def compute_full_election_sequence(
        self,
        cost: float,
        asset_type: str,
        tax_year: int = 2025,
        section_179_elected: float = 0.0,
        use_bonus: bool = True,
        year_placed_in_service: int | None = None,
    ) -> dict[str, Any]:
        """
        Run the full IRS-prescribed election sequence for a single asset purchase:
          Step 1: Section 179 (user-elected)
          Step 2: Bonus depreciation on remaining basis
          Step 3: MACRS on what's left

        Returns a comprehensive dict with all three components and the total
        first-year deduction.
        """
        if year_placed_in_service is None:
            year_placed_in_service = tax_year

        s179 = self.apply_section_179(cost, section_179_elected, tax_year)
        bonus = self.apply_bonus_depreciation(cost, s179["remaining_basis"], tax_year) if use_bonus else {
            "bonus_depreciation": 0.0,
            "remaining_basis_for_macrs": s179["remaining_basis"],
            "bonus_rate": 0.0,
        }

        macrs_basis = bonus["remaining_basis_for_macrs"]
        macrs_schedule = (
            self.compute_macrs_schedule(macrs_basis, asset_type, year_placed_in_service)
            if macrs_basis > 0 else []
        )
        first_year_macrs = macrs_schedule[0]["deduction"] if macrs_schedule else 0.0

        total_first_year = (
            s179["section_179_elected"]
            + bonus["bonus_depreciation"]
            + first_year_macrs
        )

        return {
            "cost": round(cost, 2),
            "asset_type": asset_type,
            "tax_year": tax_year,
            "section_179": s179,
            "bonus_depreciation": bonus,
            "macrs_schedule": macrs_schedule,
            "total_first_year_deduction": round(total_first_year, 2),
            "effective_first_year_rate": round(total_first_year / cost, 4) if cost > 0 else 0.0,
        }


# ── Private helpers ───────────────────────────────────────────────────────────

def _apply_rates(
    cost: float, rates: list[float], base_year: int
) -> list[dict[str, Any]]:
    """Convert a pre-computed rate table into a year-by-year schedule."""
    schedule = []
    remaining = cost
    for i, rate in enumerate(rates):
        deduction = round(cost * rate, 2)
        deduction = min(deduction, remaining)   # rounding guard
        remaining = round(remaining - deduction, 2)
        schedule.append({
            "year_number": i + 1,
            "tax_year": base_year + i,
            "deduction": deduction,
            "remaining_basis": remaining,
        })
    return schedule


def _compute_sl_schedule(
    cost: float,
    recovery_years: float,
    base_year: int,
    month_placed: int,
) -> list[dict[str, Any]]:
    """Straight-line mid-month convention for real property (27.5 / 39 year)."""
    annual_rate = _SL_ANNUAL_RATE[recovery_years]
    full_year_deduction = round(cost * annual_rate, 2)
    # First year: fraction = (12 - month_placed + 0.5) / 12
    first_year_fraction = (12 - month_placed + 0.5) / 12
    first_deduction = round(cost * annual_rate * first_year_fraction, 2)
    last_deduction = round(full_year_deduction - first_deduction + full_year_deduction * ((1 + first_year_fraction) / 1 - 1), 2)

    # Simplify: last year gets whatever basis remains
    total_years = _SL_YEARS[recovery_years]
    schedule = []
    remaining = cost

    for i in range(total_years):
        if i == 0:
            d = first_deduction
        elif i == total_years - 1:
            d = remaining   # mop up remaining basis
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


def _mid_quarter_rates(recovery_years: float, quarter: int) -> list[float]:
    """
    Return approximate mid-quarter convention rates for 5-year or 7-year property.
    IRS Rev. Proc. 87-57 Tables B and C.  Quarter = 1–4 for the quarter placed in service.
    """
    # Source: IRS Publication 946 Table A-3 (5-year) and A-4 (7-year)
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
        return _MQ_5YR.get(quarter, _MACRS_HALF_YEAR[5.0])
    if recovery_years == 7.0:
        return _MQ_7YR.get(quarter, _MACRS_HALF_YEAR[7.0])
    return list(_MACRS_HALF_YEAR.get(recovery_years, []))


def _disposal_journal_entries(
    original_cost: float,
    accum_dep: float,
    proceeds: float,
    gain_loss: float,
) -> list[dict[str, Any]]:
    """Build the journal entries for asset retirement/sale."""
    entries = [
        {"debit":  {"account": 1010, "name": "Checking Account",  "amount": round(proceeds, 2)}},
        {"debit":  {"account": 1510, "name": "Accumulated Depreciation", "amount": round(accum_dep, 2)}},
        {"credit": {"account": 1500, "name": "Equipment (Asset)",  "amount": round(original_cost, 2)}},
    ]
    if gain_loss > 0:
        entries.append({"credit": {"account": 4500, "name": "Gain on Asset Sale (Other Income)", "amount": round(gain_loss, 2)}})
    elif gain_loss < 0:
        entries.append({"debit": {"account": 7900, "name": "Loss on Asset Disposal (Other Expense)", "amount": round(abs(gain_loss), 2)}})
    return entries


def _disposal_tax_note(is_loss: bool, recaptured: float, sec_1231: float) -> str:
    if is_loss:
        return "Section 1231 loss — fully deductible as ordinary loss on Form 4797."
    parts = []
    if recaptured > 0:
        parts.append(f"${recaptured:,.2f} ordinary income (Section 1245 recapture)")
    if sec_1231 > 0:
        parts.append(f"${sec_1231:,.2f} Section 1231 gain (long-term capital gain if >1-year holding)")
    return "Form 4797 required. " + "; ".join(parts) + "."
