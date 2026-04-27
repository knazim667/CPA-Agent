from __future__ import annotations

import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from main import CPAAgent
from skills import DocumentProcessor


ROOT_DIR = Path(__file__).resolve().parent
UI_DIR = ROOT_DIR / "ui"
UPLOAD_DIR = ROOT_DIR / "uploads"

app = FastAPI(title="CPA-Agent UI")
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

agent = CPAAgent()
document_processor = DocumentProcessor(UPLOAD_DIR)
agent_lock = Lock()
pending_document_drafts: dict[str, dict[str, Any]] = {}

_DRAFT_TTL_SECONDS = 3600
_DRAFT_MAX_ENTRIES = 100


def _evict_stale_drafts() -> None:
    now = time.time()
    stale = [k for k, v in pending_document_drafts.items() if now - v.get("created_at", 0) > _DRAFT_TTL_SECONDS]
    for k in stale:
        pending_document_drafts.pop(k, None)
    if len(pending_document_drafts) > _DRAFT_MAX_ENTRIES:
        oldest = sorted(pending_document_drafts.items(), key=lambda x: x[1].get("created_at", 0))
        for k, _ in oldest[: len(pending_document_drafts) - _DRAFT_MAX_ENTRIES]:
            pending_document_drafts.pop(k, None)


class MessageRequest(BaseModel):
    message: str


class BusinessSwitchRequest(BaseModel):
    business_name: str


class ModelModeRequest(BaseModel):
    mode: str


class TransactionRequest(BaseModel):
    date: str
    description: str
    category: str
    amount: float
    entry_type: str
    reference: str = ""
    notes: str = ""


class ApprovalRequest(BaseModel):
    token: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    with agent_lock:
        return agent.get_status()


@app.post("/api/message")
def send_message(payload: MessageRequest) -> dict[str, Any]:
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


@app.post("/api/switch-business")
def switch_business(payload: BusinessSwitchRequest) -> dict[str, Any]:
    business_name = payload.business_name.strip()
    if not business_name:
        raise HTTPException(status_code=400, detail="Business name cannot be empty.")

    with agent_lock:
        try:
            profile = agent.memory.switch_business(business_name)
            agent.workspace_boot_error = None
            try:
                profile = agent.ensure_business_workspace_assets()
            except Exception as exc:  # noqa: BLE001
                agent.workspace_boot_error = str(exc)
            return {
                "ok": True,
                "message": f"Switched to {profile['business_name']}.",
                "status": agent.get_status(),
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/model-mode")
def set_model_mode(payload: ModelModeRequest) -> dict[str, Any]:
    mode = payload.mode.strip().lower()
    if mode not in {"fast", "quality"}:
        raise HTTPException(status_code=400, detail="Mode must be 'fast' or 'quality'.")

    with agent_lock:
        config = agent.set_reasoning_mode(mode)
        return {
            "ok": True,
            "message": (
                f"Reasoning mode set to {config['reasoning_mode']}. "
                f"Primary model: {config['reasoning_model']}. "
                f"Reflection model: {config['reflection_model']}."
            ),
            "status": agent.get_status(),
        }


@app.post("/api/record-transaction")
def record_transaction(payload: TransactionRequest) -> dict[str, Any]:
    with agent_lock:
        try:
            result = agent.record_structured_transaction(
                date=payload.date,
                description=payload.description,
                category=payload.category,
                amount=payload.amount,
                entry_type=payload.entry_type,
                reference=payload.reference,
                notes=payload.notes,
            )
            agent.workspace_boot_error = None
        except Exception as exc:  # noqa: BLE001
            agent.workspace_boot_error = str(exc)
            result = {
                "ok": False,
                "message": f"I could not record that transaction safely: {exc}",
            }
        return {
            "ok": result["ok"],
            "message": result["message"],
            "status": agent.get_status(),
            "presentation": agent._build_presentation(
                {
                    "details": result.get("details", {}),
                },
                agent.get_status(),
                result["message"],
            ),
        }


@app.post("/api/upload-document")
async def upload_document(
    note: str = Form(""),
    file: UploadFile = File(...),
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
                    "ok": False,
                    "message": draft["message"],
                    "status": agent.get_status(),
                    "presentation": None,
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
                "ok": True,
                "message": draft["message"],
                "status": agent.get_status(),
                "presentation": presentation,
                "document": {
                    "file_name": extracted["file_name"],
                    "file_type": extracted["file_type"],
                    "preview": extracted["preview"],
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": f"I could not process that document safely: {exc}",
                "status": agent.get_status(),
                "presentation": None,
                "document": {
                    "file_name": extracted["file_name"],
                    "file_type": extracted["file_type"],
                    "preview": extracted["preview"],
                },
            }


@app.post("/api/approve-document-draft")
def approve_document_draft(payload: ApprovalRequest) -> dict[str, Any]:
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
                draft["rows"],
                source_name=draft["file_name"],
                source_note=f"Approved from uploaded document. {draft['instruction']}".strip(),
            )
            if result["ok"]:
                pending_document_drafts.pop(token, None)
            presentation = agent._build_presentation(
                {"details": result.get("details", {})},
                agent.get_status(),
                result["message"],
            )
            return {
                "ok": result["ok"],
                "message": result["message"],
                "status": agent.get_status(),
                "presentation": presentation,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": f"I could not approve that draft safely: {exc}",
                "status": agent.get_status(),
                "presentation": None,
            }


def main() -> int:
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
