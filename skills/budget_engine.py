"""Budget Engine - Budget vs Actual tracking"""
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from uuid import uuid4


class BudgetEngine:
    def set_budget(self, category: str, amount: float, period: str, business_key: str) -> dict:
        """Set a budget for a category."""
        return {
            "id": str(uuid4()),
            "category": category,
            "amount": float(amount),
            "period": period,
            "business_key": business_key,
            "created_at": datetime.now().isoformat()
        }

    def compute_actuals(self, budgets: List[dict], ledger_rows: list, month: str) -> List[dict]:
        """Compute actuals vs budgets for a given month."""
        try:
            target_month = datetime.strptime(month, '%Y-%m')
        except:
            return []

        actuals_by_category = {}

        # Calculate actuals from ledger
        for row in ledger_rows:
            if len(row) >= 4:
                try:
                    row_date = datetime.strptime(str(row[0]), '%Y-%m-%d')
                except:
                    continue

                if row_date.year == target_month.year and row_date.month == target_month.month:
                    category = str(row[2]).strip().lower() if row[2] else "uncategorized"
                    amount = Decimal(str(row[3])).copy_abs() if row[3] else Decimal('0')
                    actuals_by_category[category] = actuals_by_category.get(category, Decimal('0')) + amount

        # Match against budgets
        results = []
        for budget in budgets:
            if budget.get('business_key') and budget.get('period') == 'monthly':
                category = budget['category'].lower()
                budget_amount = Decimal(str(budget['amount']))
                actual_amount = actuals_by_category.get(category, Decimal('0'))
                remaining = budget_amount - actual_amount
                pct = float(actual_amount / budget_amount * 100) if budget_amount > 0 else 0.0

                results.append({
                    "category": budget['category'],
                    "budget": float(budget_amount),
                    "actual": float(actual_amount),
                    "remaining": float(remaining),
                    "pct": pct
                })

        return results

    def get_alerts(self, actuals: List[dict]) -> List[dict]:
        """Get budget alerts (80% and over)."""
        alerts = []
        for actual in actuals:
            if actual['pct'] >= 80:
                alert = actual.copy()
                alert['level'] = 'warning' if actual['pct'] < 100 else 'danger'
                alerts.append(alert)
        return alerts