from __future__ import annotations

import csv
import io
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

import warnings as _warnings
if os.environ.get("SECRET_KEY", "dev-insecure-key") == "dev-insecure-key":
    _warnings.warn(
        "SECRET_KEY is using the insecure default. Set a real 64-char hex value in .env before deploying.",
        stacklevel=1,
    )

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from auth import UserManager, get_current_user, require_owner, require_owner_or_bookkeeper
from main import CPAAgent
from skills import DocumentProcessor
from skills.pdf_exporter import generate_table_pdf


ROOT_DIR = Path(__file__).resolve().parent
UI_DIR = ROOT_DIR / "ui"
UPLOAD_DIR = ROOT_DIR / "uploads"

app = FastAPI(title="CPA-Agent UI")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-insecure-key"),
    session_cookie="cpa_session",
    max_age=86400,
    https_only=False,
    same_site="lax",
)

user_manager = UserManager(ROOT_DIR / "memory" / "users.db")

app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

agent = CPAAgent()
agent.memory.migrate_business_profiles()
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


class ProviderRequest(BaseModel):
    provider: str


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


class CategoryRuleRequest(BaseModel):
    description: str
    category: str


class RecurringCreateRequest(BaseModel):
    description: str
    amount: float
    category: str
    entry_type: str
    frequency: str
    day_of_period: int
    start_date: str


class RecurringUpdateRequest(BaseModel):
    description: str | None = None
    amount: float | None = None
    category: str | None = None
    frequency: str | None = None
    day_of_period: int | None = None
    next_date: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str
    business_keys: list[str] = []


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    business_keys: list[str] | None = None


class ProfileUpdateRequest(BaseModel):
    legal_structure: Optional[str] = None
    industry: Optional[str] = None
    business_model: Optional[str] = None
    fiscal_year_start: Optional[str] = None
    accounting_basis: Optional[str] = None
    inventory_method: Optional[str] = None
    operating_states: Optional[list[str]] = None
    address: Optional[dict] = None
    contact: Optional[dict] = None
    owners: Optional[list[dict]] = None
    onboarding_complete: Optional[bool] = None
    business_name: Optional[str] = None
    federal_ein: Optional[str] = None
    state: Optional[str] = None
    default_books_currency: Optional[str] = None


@app.get("/")
def index(request: Request) -> Response:
    if user_manager.is_empty():
        return RedirectResponse(url="/setup", status_code=302)
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(UI_DIR / "index.html")


@app.get("/login")
def login_page(request: Request) -> Response:
    if not user_manager.is_empty() and request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(UI_DIR / "login.html")


@app.get("/setup")
def setup_page(request: Request) -> Response:
    if not user_manager.is_empty():
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(UI_DIR / "setup.html")


@app.get("/api/status")
def get_status(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    with agent_lock:
        return agent.get_status()


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest, request: Request) -> dict:
    user = user_manager.verify_password(payload.username.strip(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(current_user: dict = Depends(get_current_user)) -> dict:
    return {"user": current_user}


@app.get("/api/businesses/{business_key}/profile")
def get_business_profile(
    business_key: str,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        if not user_manager.can_access_business(current_user, business_key):
            raise HTTPException(status_code=403, detail="Access denied to this business.")
        try:
            profile = agent.memory.load_business_profile(business_key)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Business not found.")
        return {"ok": True, "profile": profile}


@app.put("/api/businesses/{business_key}/profile")
def update_business_profile_endpoint(
    business_key: str,
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(require_owner),
) -> dict:
    with agent_lock:
        if not user_manager.can_access_business(current_user, business_key):
            raise HTTPException(status_code=403, detail="Access denied to this business.")
        try:
            updates = {k: v for k, v in payload.model_dump().items() if v is not None}
            profile = agent.memory.update_business_profile(business_key, updates)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Business not found.")
        return {"ok": True, "profile": profile}


@app.post("/api/setup/create-owner")
def setup_create_owner(payload: CreateUserRequest, request: Request) -> dict:
    """First-run only: create the initial owner account."""
    if not user_manager.is_empty():
        raise HTTPException(status_code=403, detail="Setup already complete.")
    if payload.role != "owner":
        raise HTTPException(status_code=400, detail="First account must be owner.")
    try:
        user = user_manager.create_user(
            payload.username.strip(),
            payload.email.strip(),
            payload.password,
            "owner",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@app.get("/api/users")
def list_users(current_user: dict = Depends(require_owner)) -> dict:
    users = user_manager.list_users()
    for u in users:
        u["business_keys"] = user_manager.get_user_businesses(u["id"])
    return {"users": users}


@app.post("/api/users")
def create_user_endpoint(
    payload: CreateUserRequest,
    current_user: dict = Depends(require_owner),
) -> dict:
    if payload.role not in ("owner", "bookkeeper", "employee"):
        raise HTTPException(status_code=400, detail="Invalid role.")
    try:
        user = user_manager.create_user(
            payload.username.strip(),
            payload.email.strip(),
            payload.password,
            payload.role,
            payload.business_keys or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "user": user}


@app.put("/api/users/{user_id}")
def update_user_endpoint(
    user_id: int,
    payload: UpdateUserRequest,
    current_user: dict = Depends(require_owner),
) -> dict:
    if payload.role and payload.role not in ("owner", "bookkeeper", "employee"):
        raise HTTPException(status_code=400, detail="Invalid role.")
    user = user_manager.update_user(
        user_id,
        role=payload.role,
        is_active=payload.is_active,
        business_keys=payload.business_keys,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "user": user}


@app.delete("/api/users/{user_id}")
def deactivate_user_endpoint(
    user_id: int,
    current_user: dict = Depends(require_owner),
) -> dict:
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")
    user = user_manager.update_user(user_id, is_active=False)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True}


@app.post("/api/message")
def send_message(payload: MessageRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict[str, Any]:
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
def switch_business(payload: BusinessSwitchRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
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
def set_model_mode(payload: ModelModeRequest, current_user: dict = Depends(require_owner)) -> dict[str, Any]:
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


@app.post("/api/provider")
def set_provider(payload: ProviderRequest, current_user: dict = Depends(require_owner)) -> dict:
    provider = payload.provider.strip().lower()
    valid_providers = {"ollama", "openai", "gemini", "openrouter"}
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {', '.join(sorted(valid_providers))}.")
    with agent_lock:
        os.environ["MODEL_PROVIDER"] = provider
        agent._refresh_model_clients()
        return {"ok": True, "message": f"Provider switched to {provider}.", "status": agent.get_status()}


@app.get("/api/report/pl")
def report_pl(from_date: str = "", to_date: str = "", current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected for this business.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [r for r in data_rows if (not from_date or str(r[0]).strip() >= from_date) and (not to_date or str(r[0]).strip() <= to_date)]
        income_by_cat: dict = {}
        expense_by_cat: dict = {}
        for row in data_rows:
            if len(row) < 5:
                continue
            amount = agent._safe_float(row[3] if len(row) > 3 else 0)
            category = str(row[2]).strip() if len(row) > 2 else "Uncategorized"
            if str(row[4]).strip().lower() == "income":
                income_by_cat[category] = income_by_cat.get(category, 0.0) + amount
            else:
                expense_by_cat[category] = expense_by_cat.get(category, 0.0) + amount
        income_total = sum(income_by_cat.values())
        expense_total = sum(expense_by_cat.values())
        return {
            "business": profile["business_name"],
            "from_date": from_date or None,
            "to_date": to_date or None,
            "income_by_category": [{"category": k, "total": round(v, 2)} for k, v in sorted(income_by_cat.items())],
            "expense_by_category": [{"category": k, "total": round(v, 2)} for k, v in sorted(expense_by_cat.items())],
            "income_total": round(income_total, 2),
            "expense_total": round(expense_total, 2),
            "net": round(income_total - expense_total, 2),
        }


@app.get("/api/export/csv")
def export_csv(from_date: str = "", to_date: str = "", current_user: dict = Depends(require_owner_or_bookkeeper)):
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [r for r in data_rows if (not from_date or str(r[0]).strip() >= from_date) and (not to_date or str(r[0]).strip() <= to_date)]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(agent.LEDGER_HEADERS)
        for row in data_rows:
            writer.writerow(agent._normalize_row(row))
        output.seek(0)
        today = time.strftime("%Y-%m-%d")
        filename = f"{agent.memory.current_business_key}-ledger-{today}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/api/export/ledger/pdf")
def export_ledger_pdf(
    from_date: str = "",
    to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
):
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G"
        )
        data_rows = rows[1:] if rows and len(rows[0]) >= len(agent.LEDGER_HEADERS) and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [
                r for r in data_rows
                if (not from_date or str(r[0]).strip() >= from_date)
                and (not to_date or str(r[0]).strip() <= to_date)
            ]
        norm = [agent._normalize_row(r) for r in data_rows]
        subtitle = f"{from_date or 'start'} — {to_date or 'today'}" if (from_date or to_date) else ""
        pdf_bytes = generate_table_pdf(
            title="General Ledger",
            headers=agent.LEDGER_HEADERS,
            rows=norm,
            business_name=profile.get("business_name", ""),
            subtitle=subtitle,
        )
    today = time.strftime("%Y-%m-%d")
    filename = f"{agent.memory.current_business_key}-ledger-{today}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/export/pl/pdf")
def export_pl_pdf(
    from_date: str = "",
    to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
):
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G"
        )
        data_rows = rows[1:] if rows and len(rows[0]) >= len(agent.LEDGER_HEADERS) and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [
                r for r in data_rows
                if (not from_date or str(r[0]).strip() >= from_date)
                and (not to_date or str(r[0]).strip() <= to_date)
            ]
        income_rows = [[r[2], f"${agent._safe_float(r[3]):.2f}"] for r in data_rows if len(r) >= 5 and str(r[4]).strip().lower() == "income"]
        expense_rows = [[r[2], f"${agent._safe_float(r[3]):.2f}"] for r in data_rows if len(r) >= 5 and str(r[4]).strip().lower() != "income"]
        all_rows = [["INCOME", ""]] + income_rows + [["EXPENSES", ""]] + expense_rows
        subtitle = f"{from_date or 'start'} — {to_date or 'today'}"
        pdf_bytes = generate_table_pdf(
            title="Profit & Loss",
            headers=["Category", "Amount"],
            rows=all_rows,
            business_name=profile.get("business_name", ""),
            subtitle=subtitle,
        )
    today = time.strftime("%Y-%m-%d")
    filename = f"{agent.memory.current_business_key}-pl-{today}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/ledger")
def get_ledger(page: int = 1, page_size: int = 20, search: str = "", from_date: str = "", to_date: str = "", current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            return {"rows": [], "total_count": 0, "page": page, "page_size": page_size, "total_pages": 0}
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        filtered = []
        for row in data_rows:
            if len(row) < 2:
                continue
            date_str = str(row[0]).strip()
            if from_date and date_str < from_date:
                continue
            if to_date and date_str > to_date:
                continue
            if search:
                desc = str(row[1]).lower() if len(row) > 1 else ""
                cat = str(row[2]).lower() if len(row) > 2 else ""
                if search.lower() not in desc and search.lower() not in cat:
                    continue
            filtered.append(agent._normalize_row(row))
        total_count = len(filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return {"rows": filtered[start: start + page_size], "total_count": total_count, "page": page, "page_size": page_size, "total_pages": total_pages}


@app.post("/api/record-transaction")
def record_transaction(payload: TransactionRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict[str, Any]:
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
def approve_document_draft(payload: ApprovalRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict[str, Any]:
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


@app.get("/api/category/suggest")
def suggest_category(description: str = "", current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    with agent_lock:
        result = agent.categorization.suggest_category(description)
        return result if result else {"category": None, "confidence": 0.0, "rule_id": None}


@app.post("/api/category-rule")
def save_category_rule(payload: CategoryRuleRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        rule = agent.categorization.save_rule(payload.description, payload.category)
        agent._save_category_rules()
        return {"ok": True, "rule": rule}


@app.get("/api/recurring")
def get_recurring(current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        return {"schedules": agent.recurring.list_schedules()}


@app.post("/api/recurring")
def create_recurring(payload: RecurringCreateRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        schedule = agent.recurring.create_schedule(
            description=payload.description, amount=payload.amount,
            category=payload.category, entry_type=payload.entry_type,
            frequency=payload.frequency, day_of_period=payload.day_of_period,
            start_date=payload.start_date,
        )
        agent._save_recurring()
        return {"ok": True, "schedule": schedule}


@app.delete("/api/recurring/{schedule_id}")
def cancel_recurring(schedule_id: str, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        found = agent.recurring.cancel_schedule(schedule_id)
        if not found:
            raise HTTPException(status_code=404, detail="Schedule not found")
        agent._save_recurring()
        return {"ok": True}


@app.put("/api/recurring/{schedule_id}")
def update_recurring(schedule_id: str, payload: RecurringUpdateRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        result = agent.recurring.update_schedule(schedule_id, updates)
        if not result:
            raise HTTPException(status_code=404, detail="Schedule not found")
        agent._save_recurring()
        return {"ok": True, "schedule": result}


class BalanceSheetRequest(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class CashFlowRequest(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None


@app.get("/api/balance-sheet")
def get_balance_sheet(from_date: Optional[str] = None, to_date: Optional[str] = None, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No Google Sheet configured")

        # Read ledger data
        rows = agent.sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"],
            range_name="Ledger!A2:G1000",
        )

        # Filter by date if provided
        if from_date or to_date:
            filtered_rows = []
            for row in rows[1:]:  # Skip header
                if len(row) >= 1:
                    row_date = str(row[0])
                    if from_date and row_date < from_date:
                        continue
                    if to_date and row_date > to_date:
                        continue
                    filtered_rows.append(row)
            rows = [rows[0]] + filtered_rows  # Keep header

        # Load AR/AP data if available
        ar_ap_data = None
        try:
            ar_ap_data = agent.memory.load_ar_ap()
        except:
            pass  # AR/AP not available yet

        balance_sheet = agent.financial_statements.compute_balance_sheet(rows[1:], ar_ap_data)
        return balance_sheet


@app.get("/api/cash-flow")
def get_cash_flow(from_date: Optional[str] = None, to_date: Optional[str] = None, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No Google Sheet configured")

        # Read ledger data
        rows = agent.sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"],
            range_name="Ledger!A2:G1000",
        )

        # Filter by date if provided
        if from_date or to_date:
            filtered_rows = []
            for row in rows[1:]:  # Skip header
                if len(row) >= 1:
                    row_date = str(row[0])
                    if from_date and row_date < from_date:
                        continue
                    if to_date and row_date > to_date:
                        continue
                    filtered_rows.append(row)
            rows = [rows[0]] + filtered_rows  # Keep header

        # Use full period or specified dates
        period_start = from_date or "2026-01-01"
        period_end = to_date or datetime.now().strftime("%Y-%m-%d")

        cash_flow = agent.financial_statements.compute_cash_flow(rows[1:], period_start, period_end)
        return cash_flow


class BudgetRequest(BaseModel):
    category: str
    amount: float
    period: str


@app.get("/api/budget")
def get_budget(month: Optional[str] = None, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        if month is None:
            month = datetime.now().strftime("%Y-%m")

        budget_data = agent.memory.load_budgets()
        ledger_profile = agent.memory.get_current_business()
        if ledger_profile.get("google_sheet_id"):
            ledger_rows = agent.sheets.read_range(
                spreadsheet_id=ledger_profile["google_sheet_id"],
                range_name="Ledger!A2:G1000",
            )[1:]  # Skip header
        else:
            ledger_rows = []

        actuals = agent.budget_engine.compute_actuals(
            budget_data.get("budgets", []), ledger_rows, month
        )
        alerts = agent.budget_engine.get_alerts(actuals)

        return {
            "month": month,
            "budgets": actuals,
            "alerts": alerts
        }


@app.post("/api/budget")
def set_budget(payload: BudgetRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        budget_data = agent.memory.load_budgets()
        new_budget = agent.budget_engine.set_budget(
            payload.category, payload.amount, payload.period,
            agent.memory.current_business_key
        )
        budget_data["budgets"].append(new_budget)
        agent.memory.save_budgets(budget_data)
        return {"ok": True, "budget": new_budget}


@app.delete("/api/budget/{budget_id}")
def delete_budget(budget_id: str, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        budget_data = agent.memory.load_budgets()
        original_len = len(budget_data["budgets"])
        budget_data["budgets"] = [
            b for b in budget_data["budgets"] if b.get("id") != budget_id
        ]
        if len(budget_data["budgets"]) < original_len:
            agent.memory.save_budgets(budget_data)
            return {"ok": True}
        else:
            raise HTTPException(status_code=404, detail="Budget not found")


# AR/AP Endpoints
@app.post("/api/ar-ap")
def create_ar_ap_entry(payload: dict, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
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
                    client=client_vendor,
                    amount=float(amount),
                    due_date=due_date,
                    notes=notes
                )
            elif entry_type == "payable":
                result = agent.ar_ap_engine.add_payable(
                    vendor=client_vendor,
                    amount=float(amount),
                    due_date=due_date,
                    notes=notes
                )
            else:
                raise HTTPException(status_code=400, detail="Type must be 'receivable' or 'payable'")

            return {"ok": True, "entry": result}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/ar-ap/{entry_id}/mark-paid")
def mark_ar_ap_paid(entry_id: str, payload: dict, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            from datetime import datetime as _dt
            entry_type = payload.get("type", "receivable").lower()
            paid_date = payload.get("paid_date") or _dt.now().strftime("%Y-%m-%d")

            if entry_type not in ["receivable", "payable"]:
                raise HTTPException(status_code=400, detail="Type must be 'receivable' or 'payable'")

            entry = agent.ar_ap_engine.mark_paid(
                entry_id=entry_id,
                entry_type=entry_type,
                paid_date=paid_date,
            )

            description = (
                f"Invoice paid: {entry['client_vendor']}"
                if entry_type == "receivable"
                else f"Bill paid: {entry['client_vendor']}"
            )
            post_result = agent.record_structured_transaction(
                date=paid_date,
                description=description,
                category="Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
                amount=entry["amount"],
                entry_type="Income" if entry_type == "receivable" else "Expense",
                notes=entry.get("notes", ""),
            )
            return {"ok": True, "entry": entry, "ledger_posted": post_result.get("ok", False)}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ar-ap")
def get_ar_ap(current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            data = agent.ar_ap_engine.get_ar_ap()
            return {"ok": True, "data": data}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ar-ap/overdue")
def get_overdue_ar_ap(current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            data = agent.ar_ap_engine.get_overdue_items()
            return {"ok": True, "data": data}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/ar-ap/upcoming")
def get_upcoming_ar_ap(days_ahead: int = 7, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            data = agent.ar_ap_engine.get_upcoming_due(days_ahead=days_ahead)
            return {"ok": True, "data": data}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


# Tax Endpoints
@app.get("/api/tax")
def get_tax_info(year: int = None, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        try:
            if year is None:
                from datetime import date
                year = date.today().year

            # Get net income from ledger for current year
            ledger_rows = agent.sheets.read_range(
                spreadsheet_id=agent.memory.get_current_business()["google_sheet_id"],
                range_name="Ledger!A:G"
            )
            tax_summary = agent.tax_engine.compute_tax_summary(ledger_rows)
            quarterly_estimate = agent.tax_engine.get_quarterly_estimate(tax_summary["net_income"], year)
            deadlines = agent.tax_engine.get_irs_deadlines(year)
            upcoming_alerts = agent.tax_engine.get_upcoming_alerts()

            return {
                "ok": True,
                "year": year,
                "tax_summary": tax_summary,
                "quarterly_estimate": quarterly_estimate,
                "irs_deadlines": deadlines,
                "upcoming_alerts": upcoming_alerts
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))


# Bank Reconciliation Endpoints
@app.post("/api/reconcile/upload")
def upload_bank_statement(file: UploadFile = File(...), current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        # Save uploaded file temporarily
        temp_path = Path(f"/tmp/{file.filename}")
        with open(temp_path, "wb") as buffer:
            content = file.file.read()
            buffer.write(content)

        try:
            # Parse the bank statement
            parsed = agent.reconciliation_engine.parse_bank_statement(temp_path)

            # Get ledger data for matching
            profile = agent.memory.get_current_business()
            if not profile.get("google_sheet_id"):
                raise HTTPException(status_code=400, detail="No Google Sheet configured")

            ledger_rows = agent.sheets.read_range(
                spreadsheet_id=profile["google_sheet_id"],
                range_name="Ledger!A2:G1000",
            )

            # Match transactions
            matches = agent.reconciliation_engine.match_transactions(parsed, ledger_rows)

            # Add IDs to unmatched bank transactions for frontend reference
            unmatched_bank_with_ids = []
            for i, tx in enumerate(matches["unmatched_bank"]):
                tx_with_id = tx.copy()
                tx_with_id["id"] = str(i)  # Simple index-based ID
                unmatched_bank_with_ids.append(tx_with_id)

            return {
                "parsed_count": len(parsed),
                "matched": matches["matched"],
                "unmatched_bank": unmatched_bank_with_ids,
                "unmatched_ledger": matches["unmatched_ledger"]
            }
        finally:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)


class ReconcileResolveRequest(BaseModel):
    date: str
    description: str
    amount: float
    action: str  # "add_to_ledger" or "mark_resolved"


@app.post("/api/reconcile/resolve/{transaction_id}")
def resolve_transaction(transaction_id: str, payload: ReconcileResolveRequest, current_user: dict = Depends(require_owner_or_bookkeeper)) -> dict:
    with agent_lock:
        action = payload.action
        if action not in ["add_to_ledger", "mark_resolved"]:
            raise HTTPException(status_code=400, detail="Invalid action")

        # For now, we ignore transaction_id since we're sending the data in the request body
        # In a more robust implementation, we would use the ID to retrieve stored reconciliation data

        if action == "add_to_ledger":
            # Add the transaction to the ledger
            try:
                # Determine if it's income or expense based on amount
                entry_type = "Income" if payload.amount >= 0 else "Expense"
                # For display, we want positive amounts in the ledger
                ledger_amount = abs(payload.amount)

                result = agent.record_structured_transaction(
                    date=payload.date,
                    description=payload.description,
                    category="Uncategorized",  # Default category, user can update later
                    amount=ledger_amount,
                    entry_type=entry_type,
                    reference="",
                    notes=f"Added via bank reconciliation: {payload.description}"
                )

                if result["ok"]:
                    return {"ok": True, "message": "Transaction added to ledger"}
                else:
                    return {"ok": False, "message": f"Failed to add transaction: {result.get('message', 'Unknown error')}"}
            except Exception as exc:
                return {"ok": False, "message": f"Error adding transaction to ledger: {exc}"}
        else:
            # Mark as resolved (no action needed)
            return {"ok": True, "message": "Transaction marked as resolved"}


def main() -> int:
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
