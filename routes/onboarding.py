"""Onboarding wizard endpoints: business registration and Google OAuth."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from auth import get_current_user
from models.requests import OnboardingBusinessRequest
from routes._state import UI_DIR, agent, agent_lock, user_manager

router = APIRouter()

_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

_ROOT = Path(__file__).resolve().parent.parent


def _google_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env vars or the client secret JSON file."""
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if client_id and client_secret:
        return client_id, client_secret
    json_path = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_FILE", "")
    if json_path:
        p = Path(json_path) if Path(json_path).is_absolute() else _ROOT / json_path
        if p.exists():
            data = json.loads(p.read_text())
            cfg = data.get("web") or data.get("installed") or {}
            return cfg.get("client_id", ""), cfg.get("client_secret", "")
    return "", ""


@router.get("/onboarding")
def onboarding_page(request: Request) -> Any:
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(UI_DIR / "onboarding.html")


@router.get("/api/onboarding/status")
def onboarding_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict:
    business_keys = user_manager.get_user_businesses(current_user["id"])
    if not business_keys:
        return {"onboarding_complete": False, "google_connected": False, "business_key": None}
    business_key = business_keys[0]
    token_path = agent.memory.long_term_dir / business_key / "google_tokens.json"
    return {
        "onboarding_complete": True,
        "google_connected": token_path.exists(),
        "business_key": business_key,
    }


@router.post("/api/onboarding/business")
def onboarding_business(
    payload: OnboardingBusinessRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not payload.business_name.strip():
        raise HTTPException(status_code=400, detail="Business name is required.")
    with agent_lock:
        try:
            result = agent.memory.create_business(
                payload.business_name.strip(), state=payload.state
            )
            business_key = result[0] if isinstance(result, tuple) else result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        agent.memory.update_business_profile(business_key, {
            "legal_structure": payload.legal_structure,
            "industry": payload.industry,
            "ein": payload.ein,
            "accounting_basis": payload.accounting_basis,
            "onboarding_complete": True,
        })
    user_manager.link_business(current_user["id"], business_key)
    return {"ok": True, "business_key": business_key}


@router.get("/api/onboarding/google-auth")
def onboarding_google_auth(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict:
    client_id, client_secret = _google_credentials()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server.")
    from core.google_auth import GoogleWorkspaceAuth
    redirect_uri = str(request.base_url).rstrip("/") + "/api/onboarding/google-callback"
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    auth_url = GoogleWorkspaceAuth.build_web_auth_url(
        client_id, client_secret, redirect_uri, state, _GOOGLE_SCOPES
    )
    return {"auth_url": auth_url}


@router.get("/api/onboarding/google-callback")
def onboarding_google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
) -> Any:
    if error:
        return RedirectResponse(url="/onboarding?step=2&error=denied", status_code=302)
    stored_state = request.session.pop("oauth_state", None)
    if not stored_state or stored_state != state:
        return RedirectResponse(url="/onboarding?step=2&error=state_mismatch", status_code=302)
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    business_keys = user_manager.get_user_businesses(user_id)
    if not business_keys:
        return RedirectResponse(url="/onboarding", status_code=302)
    business_key = business_keys[0]
    client_id, client_secret = _google_credentials()
    redirect_uri = str(request.base_url).rstrip("/") + "/api/onboarding/google-callback"
    from core.google_auth import GoogleWorkspaceAuth
    try:
        credentials = GoogleWorkspaceAuth.exchange_web_auth_code(
            client_id, client_secret, redirect_uri, state, code, _GOOGLE_SCOPES
        )
    except Exception:
        return RedirectResponse(url="/onboarding?step=2&error=token_exchange_failed", status_code=302)
    token_path = agent.memory.long_term_dir / business_key / "google_tokens.json"
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    try:
        from skills.google_sheets_manager import GoogleSheetsManager
        with agent_lock:
            profile = agent.memory.load_business_profile(business_key)
            sheets = GoogleSheetsManager.from_token_path(str(token_path))
            spreadsheet = sheets.create_spreadsheet(profile.get("business_name", business_key))
            agent.memory.update_business_profile(business_key, {
                "google_sheet_id": spreadsheet["spreadsheetId"]
            })
    except Exception:
        pass
    return RedirectResponse(url="/onboarding?step=3", status_code=302)
