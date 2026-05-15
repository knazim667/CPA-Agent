"""Budget management routes."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import require_owner_or_bookkeeper
from models.requests import BudgetRequest
from routes._state import agent, agent_lock

router = APIRouter()


@router.get("/api/budget")
def get_budget(
    month: Optional[str] = None,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        budget_data = agent.memory.load_budgets()
        ledger_profile = agent.memory.get_current_business()
        if ledger_profile.get("google_sheet_id"):
            ledger_rows = agent.sheets.read_range(
                spreadsheet_id=ledger_profile["google_sheet_id"],
                range_name="Ledger!A2:G1000",
            )[1:]
        else:
            ledger_rows = []
        actuals = agent.budget_engine.compute_actuals(budget_data.get("budgets", []), ledger_rows, month)
        alerts = agent.budget_engine.get_alerts(actuals)
        return {"month": month, "budgets": actuals, "alerts": alerts}


@router.post("/api/budget")
def set_budget(
    payload: BudgetRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        budget_data = agent.memory.load_budgets()
        new_budget = agent.budget_engine.set_budget(
            payload.category, payload.amount, payload.period, agent.memory.current_business_key,
        )
        budget_data["budgets"].append(new_budget)
        agent.memory.save_budgets(budget_data)
        return {"ok": True, "budget": new_budget}


@router.delete("/api/budget/{budget_id}")
def delete_budget(
    budget_id: str,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        budget_data = agent.memory.load_budgets()
        original_len = len(budget_data["budgets"])
        budget_data["budgets"] = [b for b in budget_data["budgets"] if b.get("id") != budget_id]
        if len(budget_data["budgets"]) < original_len:
            agent.memory.save_budgets(budget_data)
            return {"ok": True}
        raise HTTPException(status_code=404, detail="Budget not found")
