"""Transaction recording, document upload, and category routes."""
from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import require_owner_or_bookkeeper
from models.requests import ApprovalRequest, CategoryRuleRequest, MessageRequest, TransactionRequest
from routes._state import (
    _evict_stale_drafts, agent, agent_lock, document_processor, pending_document_drafts,
)

router = APIRouter()


@router.post("/api/message")
def send_message(
    payload: MessageRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict[str, Any]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    with agent_lock:
        try:
            response = agent.handle_command_with_metadata(message)
            return {
                "ok": True,
                "message": response["message"],
                "status": response["status"],
                "presentation": response["presentation"],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": f"I could not complete that safely: {exc}",
                "status": agent.get_status(),
                "presentation": None,
            }


@router.post("/api/record-transaction")
def record_transaction(
    payload: TransactionRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict[str, Any]:
    with agent_lock:
        try:
            result = agent.record_structured_transaction(
                date=payload.date, description=payload.description, category=payload.category,
                amount=payload.amount, entry_type=payload.entry_type,
                reference=payload.reference, notes=payload.notes,
            )
            agent.workspace_boot_error = None
        except Exception as exc:  # noqa: BLE001
            agent.workspace_boot_error = str(exc)
            result = {"ok": False, "message": f"I could not record that transaction safely: {exc}"}
        return {
            "ok": result["ok"],
            "message": result["message"],
            "status": agent.get_status(),
            "presentation": agent._build_presentation(
                {"details": result.get("details", {})}, agent.get_status(), result["message"],
            ),
        }


@router.post("/api/upload-document")
async def upload_document(
    note: str = Form(""),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A document file is required.")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded document was empty.")
    try:
        saved_path = document_processor.save_upload(file.filename, raw)
        extracted = document_processor.extract_document(saved_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    active_business = agent.memory.get_current_business().get("business_name", "the active business")
    instruction = note.strip() or f"Review this document and record the related expense in {active_business}."

    with agent_lock:
        try:
            draft = agent.draft_document_transactions(
                file_name=extracted["file_name"],
                document_text=extracted["text"],
                instruction=instruction,
            )
            if not draft["ok"]:
                return {
                    "ok": False, "message": draft["message"],
                    "status": agent.get_status(), "presentation": None,
                    "document": {
                        "file_name": extracted["file_name"],
                        "file_type": extracted["file_type"],
                        "preview": extracted["preview"],
                    },
                }
            _evict_stale_drafts()
            token = uuid.uuid4().hex
            pending_document_drafts[token] = {
                "business_key": agent.memory.current_business_key,
                "rows": draft["details"]["rows"],
                "file_name": extracted["file_name"],
                "instruction": instruction,
                "created_at": time.time(),
            }
            presentation = {
                "kind": "document_draft",
                "title": f"Draft Expenses From {extracted['file_name']}",
                "summary_items": [
                    {"label": "Rows", "value": str(len(draft["details"]["rows"]))},
                    {"label": "Total", "value": f"${draft['details']['total_amount']:.2f}"},
                    {"label": "Business", "value": active_business},
                ],
                "table": {
                    "columns": ["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
                    "rows": draft["details"]["rows"],
                },
                "approval_token": token,
                "approval_label": "Approve And Post To Ledger",
                "document_preview": extracted["preview"][:600],
            }
            return {
                "ok": True, "message": draft["message"],
                "status": agent.get_status(), "presentation": presentation,
                "document": {
                    "file_name": extracted["file_name"],
                    "file_type": extracted["file_type"],
                    "preview": extracted["preview"],
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False, "message": f"I could not process that document safely: {exc}",
                "status": agent.get_status(), "presentation": None,
                "document": {
                    "file_name": extracted["file_name"],
                    "file_type": extracted["file_type"],
                    "preview": extracted["preview"],
                },
            }


@router.post("/api/approve-document-draft")
def approve_document_draft(
    payload: ApprovalRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict[str, Any]:
    _evict_stale_drafts()
    token = payload.token.strip()
    draft = pending_document_drafts.get(token)
    if not draft:
        raise HTTPException(status_code=404, detail="That draft is no longer available.")
    with agent_lock:
        try:
            if draft["business_key"] != agent.memory.current_business_key:
                agent.memory.switch_business(draft["business_key"])
            result = agent.record_bulk_transactions(
                draft["rows"], source_name=draft["file_name"],
                source_note=f"Approved from uploaded document. {draft['instruction']}".strip(),
            )
            if result["ok"]:
                pending_document_drafts.pop(token, None)
            presentation = agent._build_presentation(
                {"details": result.get("details", {})}, agent.get_status(), result["message"],
            )
            return {
                "ok": result["ok"], "message": result["message"],
                "status": agent.get_status(), "presentation": presentation,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False, "message": f"I could not approve that draft safely: {exc}",
                "status": agent.get_status(), "presentation": None,
            }


@router.get("/api/category/suggest")
def suggest_category(
    description: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    with agent_lock:
        result = agent.categorization.suggest_category(description)
        return result if result else {"category": None, "confidence": 0.0, "rule_id": None}


@router.post("/api/category-rule")
def save_category_rule(
    payload: CategoryRuleRequest,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        rule = agent.categorization.save_rule(payload.description, payload.category)
        agent._save_category_rules()
        return {"ok": True, "rule": rule}
