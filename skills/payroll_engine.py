from __future__ import annotations

from dataclasses import dataclass
import logging

# ── 2026 payroll constants ──────────────────────────────────────────────────
SS_WAGE_BASE = 184_500
SS_RATE = 0.062
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD = 200_000
FUTA_WAGE_BASE = 7_000
FUTA_NET_RATE = 0.006           # 6.0% gross minus 5.4% standard state credit
ALLOWANCE_ANNUAL_VALUE = 4_300  # 2026 Pub 15-T per withholding allowance

# Percentage-method brackets (annual adjusted wage, 2026 approximation)
# Tuple: (upper_bound, rate, bracket_floor, base_tax)
_BRACKETS: dict[str, list[tuple]] = {
    "single": [
        (11_925,       0.10,       0,       0.00),
        (45_525,       0.12,  11_925,   1_192.50),
        (100_525,      0.22,  45_525,   5_224.50),
        (191_950,      0.24, 100_525,  17_324.50),
        (243_725,      0.32, 191_950,  39_266.50),
        (609_350,      0.35, 243_725,  55_834.50),
        (float("inf"), 0.37, 609_350, 183_803.25),
    ],
    "married": [
        (23_850, 0.10, 0, 0.0),
        (91_050, 0.12, 23_850, 2_385.00),
        (201_050, 0.22, 91_050, 10_449.00),
        (383_900, 0.24, 201_050, 34_649.00),
        (487_450, 0.32, 383_900, 78_533.00),
        (731_200, 0.35, 487_450, 111_669.00),
        (float("inf"), 0.37, 731_200, 196_981.50),
    ],
}


# ── Private helpers ──────────────────────────────────────────────────────────

_logger = logging.getLogger(__name__)


def _compute_annual_fit(annual_adjusted_wage: float, filing_status: str) -> float:
    if annual_adjusted_wage <= 0:
        return 0.0
    brackets = _BRACKETS.get(filing_status)
    if brackets is None:
        _logger.warning("Unknown filing_status %r; defaulting to 'single'", filing_status)
        brackets = _BRACKETS["single"]
    for upper, rate, floor, base_tax in brackets:
        if annual_adjusted_wage <= upper:
            return base_tax + rate * (annual_adjusted_wage - floor)
    return 0.0


@dataclass
class EmployeePayroll:
    gross_pay: float
    fit_base: float
    fica_base: float
    federal_withholding: float
    state_withholding: float
    social_security: float
    medicare: float
    additional_medicare: float
    retirement_401k: float
    section_125_health: float
    net_pay: float


@dataclass
class EmployerBurden:
    social_security_match: float
    medicare_match: float
    futa: float
    suta: float
    total_employer_cost: float


# ── Legacy (kept for backward compatibility) ────────────────────────────────
@dataclass
class PayrollCalculation:
    gross_pay: float
    federal_withholding: float
    social_security: float
    medicare: float
    net_pay: float


def calculate_simple_payroll(gross_pay: float, federal_rate: float = 0.12) -> PayrollCalculation:
    social_security = round(gross_pay * 0.062, 2)
    medicare = round(gross_pay * 0.0145, 2)
    federal_withholding = round(gross_pay * federal_rate, 2)
    net_pay = round(gross_pay - social_security - medicare - federal_withholding, 2)
    return PayrollCalculation(
        gross_pay=gross_pay,
        federal_withholding=federal_withholding,
        social_security=social_security,
        medicare=medicare,
        net_pay=net_pay,
    )
