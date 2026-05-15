"""Tax information and estimation routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_owner_or_bookkeeper
from routes._state import agent, agent_lock

router = APIRouter()


@router.get("/api/tax")
def get_tax_info(
    year: int = None,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        try:
            if year is None:
                from datetime import date
                year = date.today().year
            ledger_rows = agent.sheets.read_range(
                spreadsheet_id=agent.memory.get_current_business()["google_sheet_id"],
                range_name="Ledger!A:G",
            )
            tax_summary = agent.tax_engine.compute_tax_summary(ledger_rows)
            quarterly_estimate = agent.tax_engine.get_quarterly_estimate(tax_summary["net_income"], year)
            deadlines = agent.tax_engine.get_irs_deadlines(year)
            upcoming_alerts = agent.tax_engine.get_upcoming_alerts()
            return {
                "ok": True, "year": year,
                "tax_summary": tax_summary,
                "quarterly_estimate": quarterly_estimate,
                "irs_deadlines": deadlines,
                "upcoming_alerts": upcoming_alerts,
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
