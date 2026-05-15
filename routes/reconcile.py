"""Bank reconciliation routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import require_owner_or_bookkeeper
from models.requests import ReconcileResolveRequest
from routes._state import agent, agent_lock

router = APIRouter()


@router.post("/api/reconcile/upload")
def upload_bank_statement(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        temp_path = Path(f"/tmp/{file.filename}")
        with open(temp_path, "wb") as buffer:
            buffer.write(file.file.read())
        try:
            parsed = agent.reconciliation_engine.parse_bank_statement(temp_path)
            profile = agent.memory.get_current_business()
            if not profile.get("google_sheet_id"):
                raise HTTPException(status_code=400, detail="No Google Sheet configured")
            ledger_rows = agent.sheets.read_range(
                spreadsheet_id=profile["google_sheet_id"],
                range_name="Ledger!A2:G1000",
            )
            matches = agent.reconciliation_engine.match_transactions(parsed, ledger_rows)
            unmatched_bank_with_ids = []
            for i, tx in enumerate(matches["unmatched_bank"]):
                tx_with_id = tx.copy()
                tx_with_id["id"] = str(i)
                unmatched_bank_with_ids.append(tx_with_id)
            return {
                "parsed_count": len(parsed),
                "matched": matches["matched"],
                "unmatched_bank": unmatched_bank_with_ids,
                "unmatched_ledger": matches["unmatched_ledger"],
            }
        finally:
            temp_path.unlink(missing_ok=True)


@router.post("/api/reconcile/resolve/{transaction_id}")
def resolve_transaction(
    transaction_id: str,
    payload: ReconcileResolveRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        action = payload.action
        if action not in ["add_to_ledger", "mark_resolved"]:
            raise HTTPException(status_code=400, detail="Invalid action")
        if action == "add_to_ledger":
            try:
                entry_type = "Income" if payload.amount >= 0 else "Expense"
                result = agent.record_structured_transaction(
                    date=payload.date, description=payload.description,
                    category="Uncategorized", amount=abs(payload.amount),
                    entry_type=entry_type, reference="",
                    notes=f"Added via bank reconciliation: {payload.description}",
                )
                if result["ok"]:
                    return {"ok": True, "message": "Transaction added to ledger"}
                return {"ok": False, "message": f"Failed to add transaction: {result.get('message', 'Unknown error')}"}
            except Exception as exc:
                return {"ok": False, "message": f"Error adding transaction to ledger: {exc}"}
        return {"ok": True, "message": "Transaction marked as resolved"}
