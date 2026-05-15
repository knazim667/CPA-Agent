"""Authentication, user management, business settings, and system-config routes."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from auth import get_current_user, require_owner, require_owner_or_bookkeeper
from models.requests import (
    BusinessSwitchRequest, CreateUserRequest, LoginRequest,
    ModelModeRequest, ProfileUpdateRequest, ProviderRequest, UpdateUserRequest,
)
from routes._state import UI_DIR, agent, agent_lock, user_manager

router = APIRouter()


@router.get("/")
def index(request: Request) -> Response:
    if user_manager.is_empty():
        return RedirectResponse(url="/setup", status_code=302)
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(UI_DIR / "index.html")


@router.get("/login")
def login_page(request: Request) -> Response:
    if not user_manager.is_empty() and request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(UI_DIR / "login.html")


@router.get("/setup")
def setup_page(request: Request) -> Response:
    if not user_manager.is_empty():
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(UI_DIR / "setup.html")


@router.get("/api/status")
def get_status(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    with agent_lock:
        return agent.get_status()


@router.post("/api/auth/login")
def auth_login(payload: LoginRequest, request: Request) -> dict:
    user = user_manager.verify_password(payload.username.strip(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@router.post("/api/auth/logout")
def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/api/auth/me")
def auth_me(current_user: dict = Depends(get_current_user)) -> dict:
    return {"user": current_user}


@router.get("/api/businesses/{business_key}/profile")
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


@router.put("/api/businesses/{business_key}/profile")
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


@router.post("/api/setup/create-owner")
def setup_create_owner(payload: CreateUserRequest, request: Request) -> dict:
    if not user_manager.is_empty():
        raise HTTPException(status_code=403, detail="Setup already complete.")
    if payload.role != "owner":
        raise HTTPException(status_code=400, detail="First account must be owner.")
    try:
        user = user_manager.create_user(
            payload.username.strip(), payload.email.strip(), payload.password, "owner",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@router.get("/api/users")
def list_users(current_user: dict = Depends(require_owner)) -> dict:
    users = user_manager.list_users()
    for u in users:
        u["business_keys"] = user_manager.get_user_businesses(u["id"])
    return {"users": users}


@router.post("/api/users")
def create_user_endpoint(
    payload: CreateUserRequest,
    current_user: dict = Depends(require_owner),
) -> dict:
    if payload.role not in ("owner", "bookkeeper", "employee"):
        raise HTTPException(status_code=400, detail="Invalid role.")
    try:
        user = user_manager.create_user(
            payload.username.strip(), payload.email.strip(), payload.password,
            payload.role, payload.business_keys or [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "user": user}


@router.put("/api/users/{user_id}")
def update_user_endpoint(
    user_id: int,
    payload: UpdateUserRequest,
    current_user: dict = Depends(require_owner),
) -> dict:
    if payload.role and payload.role not in ("owner", "bookkeeper", "employee"):
        raise HTTPException(status_code=400, detail="Invalid role.")
    user = user_manager.update_user(
        user_id, role=payload.role, is_active=payload.is_active, business_keys=payload.business_keys,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "user": user}


@router.delete("/api/users/{user_id}")
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


@router.post("/api/switch-business")
def switch_business(
    payload: BusinessSwitchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
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
            return {"ok": True, "message": f"Switched to {profile['business_name']}.", "status": agent.get_status()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/model-mode")
def set_model_mode(
    payload: ModelModeRequest,
    current_user: dict = Depends(require_owner),
) -> dict[str, Any]:
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


@router.post("/api/provider")
def set_provider(
    payload: ProviderRequest,
    current_user: dict = Depends(require_owner),
) -> dict:
    provider = payload.provider.strip().lower()
    valid_providers = {"ollama", "openai", "gemini", "openrouter"}
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider must be one of: {', '.join(sorted(valid_providers))}.")
    with agent_lock:
        os.environ["MODEL_PROVIDER"] = provider
        agent._refresh_model_clients()
        return {"ok": True, "message": f"Provider switched to {provider}.", "status": agent.get_status()}
