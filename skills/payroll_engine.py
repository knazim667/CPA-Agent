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


def _compute_fica_employee(
    fica_base: float, ytd_wages: float
) -> tuple[float, float, float]:
    ss_remaining = max(0.0, SS_WAGE_BASE - ytd_wages)
    ss_taxable = min(fica_base, ss_remaining)
    social_security = round(ss_taxable * SS_RATE, 2)
    medicare = round(fica_base * MEDICARE_RATE, 2)

    ytd_after = ytd_wages + fica_base
    if ytd_after > ADDITIONAL_MEDICARE_THRESHOLD:
        taxable_additional = ytd_after - max(ADDITIONAL_MEDICARE_THRESHOLD, ytd_wages)
        additional_medicare = round(taxable_additional * ADDITIONAL_MEDICARE_RATE, 2)
    else:
        additional_medicare = 0.0

    return social_security, medicare, additional_medicare


def _compute_employer_taxes(
    fica_base: float,
    ytd_wages: float,
    suta_rate: float,
) -> tuple[float, float, float, float]:
    ss_remaining = max(0.0, SS_WAGE_BASE - ytd_wages)
    ss_taxable = min(fica_base, ss_remaining)
    ss_match = round(ss_taxable * SS_RATE, 2)
    medicare_match = round(fica_base * MEDICARE_RATE, 2)

    futa_remaining = max(0.0, FUTA_WAGE_BASE - ytd_wages)
    futa_taxable = min(fica_base, futa_remaining)
    futa = round(futa_taxable * FUTA_NET_RATE, 2)
    suta = round(futa_taxable * suta_rate, 2)

    return ss_match, medicare_match, futa, suta


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


# ── Public API ───────────────────────────────────────────────────────────────

def compute_net_pay(
    gross_pay: float,
    retirement_401k: float = 0.0,
    section_125_health: float = 0.0,
    filing_status: str = "single",
    allowances: int = 0,
    ytd_wages: float = 0.0,
    pay_periods_per_year: int = 26,
    state_rate: float = 0.0,
    suta_rate: float = 0.0,
) -> tuple[EmployeePayroll, EmployerBurden]:
    fica_base = max(0.0, gross_pay - section_125_health)
    fit_base = max(0.0, fica_base - retirement_401k)

    annual_fit_base = fit_base * pay_periods_per_year
    adjusted = annual_fit_base - allowances * ALLOWANCE_ANNUAL_VALUE
    annual_fit = _compute_annual_fit(adjusted, filing_status)
    federal_withholding = round(max(0.0, annual_fit / pay_periods_per_year), 2)

    state_withholding = round(fit_base * state_rate, 2)

    social_security, medicare, additional_medicare = _compute_fica_employee(
        fica_base, ytd_wages
    )
    ss_match, medicare_match, futa, suta = _compute_employer_taxes(
        fica_base, ytd_wages, suta_rate
    )

    net_pay = round(
        gross_pay
        - federal_withholding
        - state_withholding
        - social_security
        - medicare
        - additional_medicare
        - retirement_401k
        - section_125_health,
        2,
    )
    total_employer_cost = round(gross_pay + ss_match + medicare_match + futa + suta, 2)

    employee = EmployeePayroll(
        gross_pay=gross_pay,
        fit_base=fit_base,
        fica_base=fica_base,
        federal_withholding=federal_withholding,
        state_withholding=state_withholding,
        social_security=social_security,
        medicare=medicare,
        additional_medicare=additional_medicare,
        retirement_401k=retirement_401k,
        section_125_health=section_125_health,
        net_pay=net_pay,
    )
    employer = EmployerBurden(
        social_security_match=ss_match,
        medicare_match=medicare_match,
        futa=futa,
        suta=suta,
        total_employer_cost=total_employer_cost,
    )
    return employee, employer


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
