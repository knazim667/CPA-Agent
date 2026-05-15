"""Recurring transaction schedule routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_owner_or_bookkeeper
from models.requests import RecurringCreateRequest, RecurringUpdateRequest
from routes._state import agent, agent_lock

router = APIRouter()


@router.get("/api/recurring")
def get_recurring(current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        return {"schedules": agent.recurring.list_schedules()}


@router.post("/api/recurring")
def create_recurring(
    payload: RecurringCreateRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        schedule = agent.recurring.create_schedule(
            description=payload.description, amount=payload.amount,
            category=payload.category, entry_type=payload.entry_type,
            frequency=payload.frequency, day_of_period=payload.day_of_period,
            start_date=payload.start_date,
        )
        agent._save_recurring()
        return {"ok": True, "schedule": schedule}


@router.delete("/api/recurring/{schedule_id}")
def cancel_recurring(
    schedule_id: str,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        found = agent.recurring.cancel_schedule(schedule_id)
        if not found:
            raise HTTPException(status_code=404, detail="Schedule not found")
        agent._save_recurring()
        return {"ok": True}


@router.put("/api/recurring/{schedule_id}")
def update_recurring(
    schedule_id: str,
    payload: RecurringUpdateRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        result = agent.recurring.update_schedule(schedule_id, updates)
        if not result:
            raise HTTPException(status_code=404, detail="Schedule not found")
        agent._save_recurring()
        return {"ok": True, "schedule": result}
