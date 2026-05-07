import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills'))

from payroll_engine import (
    EmployeePayroll,
    EmployerBurden,
    SS_WAGE_BASE,
    MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD,
    FUTA_WAGE_BASE,
    ALLOWANCE_ANNUAL_VALUE,
)


def test_constants_2026():
    assert SS_WAGE_BASE == 184_500
    assert MEDICARE_RATE == 0.0145
    assert ADDITIONAL_MEDICARE_THRESHOLD == 200_000
    assert FUTA_WAGE_BASE == 7_000
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
    assert ep.fica_base == 4800.0
    assert ep.fit_base == 4500.0


def test_employer_burden_fields():
    eb = EmployerBurden(
        social_security_match=297.60,
        medicare_match=69.60,
        futa=30.0,
        suta=135.0,
        total_employer_cost=5532.20,
    )
    assert eb.total_employer_cost == 5532.20
