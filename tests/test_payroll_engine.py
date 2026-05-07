import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from payroll_engine import (
    EmployeePayroll,
    EmployerBurden,
    SS_WAGE_BASE,
    SS_RATE,
    MEDICARE_RATE,
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD,
    FUTA_WAGE_BASE,
    FUTA_NET_RATE,
    ALLOWANCE_ANNUAL_VALUE,
    _BRACKETS,
    _compute_annual_fit,
    _compute_fica_employee,
    _compute_employer_taxes,
    compute_net_pay,
    calculate_simple_payroll,
    PayrollCalculation,
)


def test_constants_2026():
    assert SS_WAGE_BASE == 184_500
    assert SS_RATE == 0.062
    assert MEDICARE_RATE == 0.0145
    assert ADDITIONAL_MEDICARE_RATE == 0.009
    assert ADDITIONAL_MEDICARE_THRESHOLD == 200_000
    assert FUTA_WAGE_BASE == 7_000
    assert FUTA_NET_RATE == 0.006
    assert ALLOWANCE_ANNUAL_VALUE == 4_300


def test_employee_payroll_fields():
    ep = EmployeePayroll(
        gross_pay=5000.0,
        fit_base=4500.0,
        fica_base=4800.0,
        federal_withholding=779.48,
        state_withholding=225.0,
        social_security=297.60,
        medicare=69.60,
        additional_medicare=0.0,
        retirement_401k=300.0,
        section_125_health=200.0,
        net_pay=3128.32,
    )
    assert ep.gross_pay == 5000.0
    assert ep.fit_base == 4500.0
    assert ep.fica_base == 4800.0
    assert ep.federal_withholding == 779.48
    assert ep.state_withholding == 225.0
    assert ep.social_security == 297.60
    assert ep.medicare == 69.60
    assert ep.additional_medicare == 0.0
    assert ep.retirement_401k == 300.0
    assert ep.section_125_health == 200.0
    assert ep.net_pay == 3128.32


def test_employer_burden_fields():
    eb = EmployerBurden(
        social_security_match=297.60,
        medicare_match=69.60,
        futa=30.0,
        suta=135.0,
        total_employer_cost=5532.20,
    )
    assert eb.total_employer_cost == 5532.20


def test_bracket_base_tax_consistency():
    for status, rows in _BRACKETS.items():
        for i in range(1, len(rows)):
            prev_upper, prev_rate, prev_floor, prev_base = rows[i - 1]
            _, _, _, curr_base = rows[i]
            expected = round(prev_base + (prev_upper - prev_floor) * prev_rate, 2)
            assert abs(curr_base - expected) < 0.01, (
                f"{status} bracket {i}: expected base_tax={expected}, got {curr_base}"
            )


# ── Task 2: FIT percentage-method helper tests ────────────────────────────────


def test_fit_zero_wage():
    assert _compute_annual_fit(0, "single") == 0.0
    assert _compute_annual_fit(-100, "single") == 0.0


def test_fit_single_10pct_bracket():
    # $5,000 annual → 10% bracket (0 to 11,925)
    result = _compute_annual_fit(5_000, "single")
    assert result == pytest.approx(500.0, abs=0.01)


def test_fit_single_22pct_bracket():
    # $78,000 annual → 22% bracket (45,525 to 100,525)
    # Corrected: 5224.50 + 0.22 * (78000 - 45525) = 5224.50 + 7144.50 = 12369.00
    result = _compute_annual_fit(78_000, "single")
    assert result == pytest.approx(12_369.00, abs=0.01)


def test_fit_single_24pct_bracket():
    # $112,700 annual → 24% bracket (100,525 to 191,950)
    # Corrected: 17324.50 + 0.24 * (112700 - 100525) = 17324.50 + 2922.00 = 20246.50
    result = _compute_annual_fit(112_700, "single")
    assert result == pytest.approx(20_246.50, abs=0.01)


def test_fit_married_10pct_bracket():
    # $10,000 annual married → 10% bracket (0 to 23,850)
    result = _compute_annual_fit(10_000, "married")
    assert result == pytest.approx(1_000.0, abs=0.01)


def test_fit_unknown_filing_status_falls_back_to_single():
    result_single = _compute_annual_fit(50_000, "single")
    result_unknown = _compute_annual_fit(50_000, "head_of_household")
    assert result_single == result_unknown


# ── Task 3: FICA employee helper tests ───────────────────────────────────────


def test_fica_standard_no_ytd():
    # fica_base=4800, ytd=0 → full SS + Medicare, no additional Medicare
    ss, med, add_med = _compute_fica_employee(4_800, 0.0)
    assert ss == pytest.approx(297.60, abs=0.01)
    assert med == pytest.approx(69.60, abs=0.01)
    assert add_med == 0.0


def test_fica_ss_cap_mid_paycheck():
    # ytd=184000, fica_base=1000 → only $500 is under the $184,500 cap
    ss, med, add_med = _compute_fica_employee(1_000, 184_000)
    assert ss == pytest.approx(31.00, abs=0.01)   # 500 * 0.062
    assert med == pytest.approx(14.50, abs=0.01)  # 1000 * 0.0145


def test_fica_ss_cap_fully_exceeded():
    # ytd already at or above SS_WAGE_BASE → zero SS
    ss, med, add_med = _compute_fica_employee(5_000, 184_500)
    assert ss == 0.0
    assert med == pytest.approx(72.50, abs=0.01)  # 5000 * 0.0145


def test_fica_additional_medicare_crosses_threshold():
    # ytd=199500, fica_base=1000 → $500 crosses $200k threshold
    ss, med, add_med = _compute_fica_employee(1_000, 199_500)
    # ytd_after = 200500; taxable_additional = 200500 - 200000 = 500
    assert add_med == pytest.approx(4.50, abs=0.01)  # 500 * 0.009


def test_fica_additional_medicare_fully_above_threshold():
    # ytd=201000, fica_base=1000 → entire $1000 subject to additional Medicare
    ss, med, add_med = _compute_fica_employee(1_000, 201_000)
    assert add_med == pytest.approx(9.00, abs=0.01)  # 1000 * 0.009


def test_fica_no_additional_medicare_below_threshold():
    # ytd=0, low earner → no additional Medicare
    _, _, add_med = _compute_fica_employee(5_000, 0.0)
    assert add_med == 0.0


# ── Task 4: Employer taxes helper tests ──────────────────────────────────────


def test_employer_taxes_standard():
    # fica_base=4800, ytd=0, suta=0.027
    ss_m, med_m, futa, suta = _compute_employer_taxes(4_800, 0.0, 0.027)
    assert ss_m == pytest.approx(297.60, abs=0.01)    # 4800 * 0.062
    assert med_m == pytest.approx(69.60, abs=0.01)    # 4800 * 0.0145
    assert futa == pytest.approx(28.80, abs=0.01)     # 4800 * 0.006
    assert suta == pytest.approx(129.60, abs=0.01)    # 4800 * 0.027


def test_employer_futa_cap_mid_paycheck():
    # ytd=6500 → only $500 of $7000 FUTA base remains
    _, _, futa, suta = _compute_employer_taxes(1_000, 6_500, 0.03)
    assert futa == pytest.approx(3.00, abs=0.01)   # 500 * 0.006
    assert suta == pytest.approx(15.00, abs=0.01)  # 500 * 0.03


def test_employer_futa_cap_fully_exceeded():
    # ytd >= 7000 → zero FUTA and SUTA
    _, _, futa, suta = _compute_employer_taxes(5_000, 7_000, 0.03)
    assert futa == 0.0
    assert suta == 0.0


def test_employer_ss_match_respects_wage_base():
    # ytd=184000, fica_base=5000 → only $500 SS-taxable for employer too
    ss_m, med_m, _, _ = _compute_employer_taxes(5_000, 184_000, 0.0)
    assert ss_m == pytest.approx(31.00, abs=0.01)   # 500 * 0.062
    assert med_m == pytest.approx(72.50, abs=0.01)  # 5000 * 0.0145 (no cap)


def test_employer_no_additional_medicare_match():
    # Employer does NOT pay the 0.9% additional Medicare — only employee does
    # ytd > SS_WAGE_BASE so ss_m = 0; check medicare_match = 1.45% only (not 2.35%)
    ss_m, med_m, _, _ = _compute_employer_taxes(10_000, 201_000, 0.0)
    assert ss_m == 0.0
    assert med_m == pytest.approx(145.00, abs=0.01)  # 10000 * 0.0145 only


# ── Task 5: compute_net_pay integration tests ─────────────────────────────────


def test_compute_net_pay_happy_path():
    # gross=5000, 401k=300, s125=200, single, 1 allowance, biweekly, state=5%, suta=2.7%
    emp, er = compute_net_pay(
        gross_pay=5_000,
        retirement_401k=300,
        section_125_health=200,
        filing_status="single",
        allowances=1,
        ytd_wages=0,
        pay_periods_per_year=26,
        state_rate=0.05,
        suta_rate=0.027,
    )
    assert emp.fica_base == pytest.approx(4_800, abs=0.01)
    assert emp.fit_base == pytest.approx(4_500, abs=0.01)
    # FIT: annual_fit_base=117000, adjusted=112700 (1 allowance * 4300)
    # 24% bracket: 17324.50 + 0.24*(112700-100525) = 17324.50+2922 = 20246.50; /26 = 778.71
    assert emp.federal_withholding == pytest.approx(778.71, abs=0.02)
    assert emp.state_withholding == pytest.approx(225.00, abs=0.01)   # 4500*0.05
    assert emp.social_security == pytest.approx(297.60, abs=0.01)     # 4800*0.062
    assert emp.medicare == pytest.approx(69.60, abs=0.01)             # 4800*0.0145
    assert emp.additional_medicare == 0.0
    # net = 5000 - 778.71 - 225.00 - 297.60 - 69.60 - 0 - 300 - 200 = 3129.09
    assert emp.net_pay == pytest.approx(3_129.09, abs=0.02)

    assert er.social_security_match == pytest.approx(297.60, abs=0.01)
    assert er.medicare_match == pytest.approx(69.60, abs=0.01)
    assert er.futa == pytest.approx(28.80, abs=0.01)       # 4800*0.006 (fica_base, under 7k cap)
    assert er.suta == pytest.approx(129.60, abs=0.01)      # 4800*0.027
    # total = 5000 + 297.60 + 69.60 + 28.80 + 129.60 = 5525.60
    assert er.total_employer_cost == pytest.approx(5_525.60, abs=0.02)


def test_compute_net_pay_zero_deductions():
    # No pre-tax deductions, no state, single, 0 allowances, biweekly
    emp, er = compute_net_pay(gross_pay=3_000, pay_periods_per_year=26)
    assert emp.fica_base == 3_000
    assert emp.fit_base == 3_000
    # Annual: 78000 → 22% bracket: 5224.50 + 0.22*(78000-45525) = 5224.50+7144.50 = 12369.00
    # Per period: 12369.00/26 = 475.73
    assert emp.federal_withholding == pytest.approx(475.73, abs=0.02)
    assert emp.social_security == pytest.approx(186.00, abs=0.01)
    assert emp.medicare == pytest.approx(43.50, abs=0.01)
    # net = 3000 - 475.73 - 186.00 - 43.50 = 2294.77
    assert emp.net_pay == pytest.approx(2_294.77, abs=0.02)


def test_compute_net_pay_ss_cap_mid_period():
    emp, er = compute_net_pay(gross_pay=1_000, ytd_wages=184_000)
    assert emp.social_security == pytest.approx(31.00, abs=0.01)
    assert er.social_security_match == pytest.approx(31.00, abs=0.01)


def test_compute_net_pay_additional_medicare():
    emp, _ = compute_net_pay(gross_pay=1_000, ytd_wages=199_500)
    assert emp.additional_medicare == pytest.approx(4.50, abs=0.01)


def test_compute_net_pay_returns_correct_types():
    from payroll_engine import EmployeePayroll, EmployerBurden
    emp, er = compute_net_pay(gross_pay=5_000)
    assert isinstance(emp, EmployeePayroll)
    assert isinstance(er, EmployerBurden)


# ── Task 6: Backward-compat regression tests for calculate_simple_payroll ─────


def test_calculate_simple_payroll_unchanged():
    result = calculate_simple_payroll(3_000)
    assert isinstance(result, PayrollCalculation)
    assert result.gross_pay == 3_000
    assert result.federal_withholding == pytest.approx(360.00, abs=0.01)  # 3000 * 0.12
    assert result.social_security == pytest.approx(186.00, abs=0.01)      # 3000 * 0.062
    assert result.medicare == pytest.approx(43.50, abs=0.01)              # 3000 * 0.0145
    assert result.net_pay == pytest.approx(2_410.50, abs=0.01)            # 3000 - 360 - 186 - 43.50


def test_calculate_simple_payroll_custom_rate():
    result = calculate_simple_payroll(5_000, federal_rate=0.22)
    assert result.federal_withholding == pytest.approx(1_100.00, abs=0.01)
    assert result.net_pay == pytest.approx(3_517.50, abs=0.01)            # 5000 - 1100 - 310 - 72.50
