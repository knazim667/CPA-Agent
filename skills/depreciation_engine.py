"""MACRS depreciation engine for LLC assets — Section 179, bonus, and disposal."""
from __future__ import annotations

from typing import Any

from skills.depreciation_constants import (
    BONUS_DEPRECIATION_RATES, MACRS_HALF_YEAR, RECOVERY_PERIODS, SECTION_179_LIMITS,
    SL_ANNUAL_RATE, SL_YEARS, DepreciationYear,
    apply_rates as _apply_rates,
    compute_sl_schedule as _compute_sl_schedule,
    mid_quarter_rates as _mid_quarter_rates,
    disposal_journal_entries as _disposal_journal_entries,
    disposal_tax_note as _disposal_tax_note,
)


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

        if recovery in MACRS_HALF_YEAR:
            rates = list(MACRS_HALF_YEAR[recovery])
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

