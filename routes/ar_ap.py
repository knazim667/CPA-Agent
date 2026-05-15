"""Accounts receivable and payable routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from auth import require_owner_or_bookkeeper
from routes._state import agent, agent_lock

router = APIRouter()


@router.post("/api/ar-ap")
def create_ar_ap_entry(
    payload: dict,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        try:
            entry_type = payload.get("type", "receivable").lower()
            client_vendor = payload.get("client_vendor", "").strip()
            amount = payload.get("amount")
            due_date = payload.get("due_date")
            notes = payload.get("notes", "")
            if not client_vendor:
                raise HTTPException(status_code=400, detail="Client/Vendor name is required")
            if amount is None:
                raise HTTPException(status_code=400, detail="Amount is required")
            if not due_date:
                raise HTTPException(status_code=400, detail="Due date is required")
            if entry_type == "receivable":
                result = agent.ar_ap_engine.add_receivable(
                    client=client_vendor, amount=float(amount), due_date=due_date, notes=notes,
                )
            elif entry_type == "payable":
                result = agent.ar_ap_engine.add_payable(
                    vendor=client_vendor, amount=float(amount), due_date=due_date, notes=notes,
                )
            else:
                raise HTTPException(status_code=400, detail="Type must be 'receivable' or 'payable'")
            return {"ok": True, "entry": result}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.put("/api/ar-ap/{entry_id}/mark-paid")
def mark_ar_ap_paid(
    entry_id: str,
    payload: dict,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        try:
            entry_type = payload.get("type", "receivable").lower()
            paid_date = payload.get("paid_date") or datetime.now().strftime("%Y-%m-%d")
            if entry_type not in ["receivable", "payable"]:
                raise HTTPException(status_code=400, detail="Type must be 'receivable' or 'payable'")
            entry = agent.ar_ap_engine.mark_paid(
                entry_id=entry_id, entry_type=entry_type, paid_date=paid_date,
            )
            description = (
                f"Invoice paid: {entry['client_vendor']}"
                if entry_type == "receivable"
                else f"Bill paid: {entry['client_vendor']}"
            )
            post_result = agent.record_structured_transaction(
                date=paid_date, description=description,
                category="Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
                amount=entry["amount"],
                entry_type="Income" if entry_type == "receivable" else "Expense",
                notes=entry.get("notes", ""),
            )
            return {"ok": True, "entry": entry, "ledger_posted": post_result.get("ok", False)}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/ar-ap")
def get_ar_ap(current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            data = agent.ar_ap_engine.get_ar_ap()
            return {"ok": True, "data": data}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/ar-ap/overdue")
def get_overdue_ar_ap(current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            data = agent.ar_ap_engine.get_overdue_items()
            return {"ok": True, "data": data}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/ar-ap/upcoming")
def get_upcoming_ar_ap(
    days_ahead: int = 7,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        try:
            data = agent.ar_ap_engine.get_upcoming_due(days_ahead=days_ahead)
            return {"ok": True, "data": data}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
