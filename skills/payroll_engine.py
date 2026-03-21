from __future__ import annotations

from dataclasses import dataclass


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
