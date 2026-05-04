from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import json


@dataclass
class TaxEstimate:
    se_tax: float  # Self-employment tax
    federal_tax: float  # Estimated federal income tax
    total: float  # Total estimated tax
    due_date: str  # YYYY-MM-DD format
    year: int  # Tax year
    quarter: str  # Q1, Q2, Q3, or Q4


@dataclass
class IRSDeadline:
    deadline: str  # YYYY-MM-DD format
    description: str
    quarter: str  # Q1, Q2, Q3, Q4, or Annual
    year: int


class TaxEngine:
    def __init__(self, memory_manager):
        self.memory = memory_manager

    def compute_se_tax(self, net_income: float) -> float:
        """
        Compute self-employment tax: 15.3% of 92.35% of net income
        """
        if net_income <= 0:
            return 0.0
        return net_income * 0.9235 * 0.153

    # 2026 single-filer brackets: (width, rate)
    _FEDERAL_BRACKETS = [
        (11_600,              0.10),
        (47_300  - 11_600,   0.12),
        (95_375  - 47_300,   0.22),
        (182_100 - 95_375,   0.24),
        (231_250 - 182_100,  0.32),
        (578_125 - 231_250,  0.35),
        (float("inf"),        0.37),
    ]

    def compute_estimated_federal(self, net_income: float) -> float:
        if net_income <= 0:
            return 0.0
        tax = 0.0
        remaining = net_income
        for width, rate in self._FEDERAL_BRACKETS:
            if remaining <= 0:
                break
            taxable = min(remaining, width)
            tax += taxable * rate
            remaining -= taxable
        return tax

    def get_quarterly_estimate(self, net_income: float, year: int) -> Dict[str, Any]:
        """
        Get quarterly tax estimate for the given year
        Returns dict with se_tax, federal_tax, total, and due_date for next quarter
        """
        se_tax = self.compute_se_tax(net_income)
        federal_tax = self.compute_estimated_federal(net_income)
        total = se_tax + federal_tax

        # Determine next quarter due date
        today = date.today()
        if today.month <= 3:
            # Q1 due April 15
            due_date = f"{year}-04-15"
            quarter = "Q1"
        elif today.month <= 5:
            # Q2 due June 15
            due_date = f"{year}-06-15"
            quarter = "Q2"
        elif today.month <= 8:
            # Q3 due September 15
            due_date = f"{year}-09-15"
            quarter = "Q3"
        else:
            # Q4 due January 15 of next year
            due_date = f"{year + 1}-01-15"
            quarter = "Q4"

        return {
            "se_tax": round(se_tax, 2),
            "federal_tax": round(federal_tax, 2),
            "total": round(total, 2),
            "due_date": due_date,
            "quarter": quarter,
            "year": year
        }

    def get_irs_deadlines(self, year: int) -> List[Dict[str, Any]]:
        """
        Get IRS deadlines for the given tax year
        """
        deadlines = [
            {
                "deadline": f"{year}-04-15",
                "description": "Q1 Estimated Tax Payment",
                "quarter": "Q1",
                "year": year
            },
            {
                "deadline": f"{year}-06-15",
                "description": "Q2 Estimated Tax Payment",
                "quarter": "Q2",
                "year": year
            },
            {
                "deadline": f"{year}-09-15",
                "description": "Q3 Estimated Tax Payment",
                "quarter": "Q3",
                "year": year
            },
            {
                "deadline": f"{year + 1}-01-15",
                "description": "Q4 Estimated Tax Payment",
                "quarter": "Q4",
                "year": year
            },
            {
                "deadline": f"{year + 1}-04-15",
                "description": "Annual Tax Return Due",
                "quarter": "Annual",
                "year": year
            }
        ]
        return deadlines

    def get_upcoming_alerts(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """
        Get upcoming tax alerts within the next N days
        """
        today = date.today()
        target_date = today + timedelta(days=days_ahead)

        # Get current year deadlines
        current_year = today.year
        deadlines = self.get_irs_deadlines(current_year)

        upcoming = []
        for deadline in deadlines:
            deadline_date = datetime.strptime(deadline["deadline"], "%Y-%m-%d").date()
            if today <= deadline_date <= target_date:
                days_until = (deadline_date - today).days
                deadline_copy = deadline.copy()
                deadline_copy["days_until"] = days_until
                upcoming.append(deadline_copy)

        return upcoming

    def compute_tax_summary(self, ledger_rows: List[List]) -> Dict[str, Any]:
        """
        Compute tax summary from ledger rows
        Expected ledger format: [Date, Description, Category, Amount, Type, Reference, Notes]
        Indices: 0=Date, 1=Description, 2=Category, 3=Amount, 4=Type
        """
        total_income = 0.0
        total_expenses = 0.0

        for row in ledger_rows:
            if len(row) >= 5:
                entry_type = str(row[4]).strip() if row[4] else ""
                try:
                    amount = float(str(row[3]).replace(",", "").replace("$", "")) if row[3] else 0.0
                except (ValueError, TypeError):
                    amount = 0.0

                if entry_type.lower() == "income":
                    total_income += amount
                elif entry_type.lower() == "expense":
                    total_expenses += amount

        net_income = total_income - total_expenses
        se_tax = self.compute_se_tax(net_income)
        federal_tax = self.compute_estimated_federal(net_income)
        total_tax = se_tax + federal_tax

        return {
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_income": round(net_income, 2),
            "se_tax": round(se_tax, 2),
            "federal_tax": round(federal_tax, 2),
            "total_tax": round(total_tax, 2),
            "estimated_quarterly_payment": round(total_tax / 4, 2)
        }