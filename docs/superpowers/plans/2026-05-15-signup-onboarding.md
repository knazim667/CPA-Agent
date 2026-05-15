# Signup & Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-time `/setup` page with a public signup + 3-step onboarding wizard (business details → Google OAuth → done), gating the dashboard behind `onboarding_complete`.

**Architecture:** `routes/onboarding.py` (new) handles the wizard endpoints; `routes/auth.py` gains signup page + API and the updated `/` redirect logic. `GoogleWorkspaceAuth` gains two static methods for the web OAuth flow. Per-business tokens live in `memory/long_term/{key}/google_tokens.json`.

**Tech Stack:** FastAPI, Starlette sessions, google-auth-oauthlib (already in requirements.txt), Pydantic, vanilla JS (existing pattern), SQLite (UserManager).

---

## File Map

| File | Action |
|------|--------|
| `models/requests.py` | Add `SignupRequest`, `OnboardingBusinessRequest` |
| `auth.py` | Add `UserManager.link_business()` |
| `core/google_auth.py` | Add `build_web_auth_url()`, `exchange_web_auth_code()` static methods; add `token_path` param |
| `skills/google_sheets_manager.py` | Add `from_token_path()` classmethod |
| `routes/onboarding.py` | **Create** — 5 new endpoints |
| `routes/auth.py` | Fix `/` redirect, add `/signup` page + API, retire `/setup` |
| `web_app.py` | Include `onboarding_router` |
| `ui/signup.html` | **Create** |
| `ui/login.html` | Add "Sign up" link |
| `ui/onboarding.html` | **Create** — 3-step JS wizard |
| `ui/setup.html` | **Delete** |
| `tests/test_signup_models.py` | **Create** |

---

## Task 1: Request Models

**Files:**
- Modify: `models/requests.py`
- Create: `tests/test_signup_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signup_models.py
from __future__ import annotations
import pytest
from pydantic import ValidationError
from models.requests import SignupRequest, OnboardingBusinessRequest


def test_signup_request_valid():
    r = SignupRequest(username="alice", email="a@b.com", password="secret123", confirm_password="secret123")
    assert r.username == "alice"
    assert r.email == "a@b.com"


def test_signup_request_missing_confirm_password_raises():
    with pytest.raises(ValidationError):
        SignupRequest(username="alice", email="a@b.com", password="secret123")


def test_onboarding_business_request_defaults():
    r = OnboardingBusinessRequest(business_name="Acme", legal_structure="s_corp", industry="retail")
    assert r.ein == ""
    assert r.state == ""
    assert r.accounting_basis == "cash"


def test_onboarding_business_request_all_fields():
    r = OnboardingBusinessRequest(
        business_name="Acme LLC",
        legal_structure="single_member_llc",
        industry="e_commerce",
        ein="12-3456789",
        state="CA",
        accounting_basis="accrual",
    )
    assert r.ein == "12-3456789"
    assert r.state == "CA"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_signup_models.py -v
```
Expected: FAIL — `cannot import name 'SignupRequest'`

- [ ] **Step 3: Add the two models to `models/requests.py`**

Open `models/requests.py` and append before the final blank line:

```python
class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: str


class OnboardingBusinessRequest(BaseModel):
    business_name: str
    legal_structure: str
    industry: str
    ein: str = ""
    state: str = ""
    accounting_basis: str = "cash"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_signup_models.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add models/requests.py tests/test_signup_models.py
git commit -m "feat: add SignupRequest and OnboardingBusinessRequest models"
```

---

## Task 2: UserManager.link_business()

**Files:**
- Modify: `auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auth.py`:

```python
def test_link_business_stores_key(um):
    user = um.create_user("charlie", "c@example.com", "password1", "owner")
    um.link_business(user["id"], "nazam_llc")
    assert "nazam_llc" in um.get_user_businesses(user["id"])


def test_link_business_duplicate_is_idempotent(um):
    user = um.create_user("diana", "d@example.com", "password1", "owner")
    um.link_business(user["id"], "biz1")
    um.link_business(user["id"], "biz1")  # second call must not raise
    assert um.get_user_businesses(user["id"]).count("biz1") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_auth.py::test_link_business_stores_key tests/test_auth.py::test_link_business_duplicate_is_idempotent -v
```
Expected: FAIL — `AttributeError: 'UserManager' object has no attribute 'link_business'`

- [ ] **Step 3: Add `link_business` to `UserManager` in `auth.py`**

Add this method to the `UserManager` class, after `get_user_businesses`:

```python
def link_business(self, user_id: int, business_key: str) -> None:
    with self._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_businesses (user_id, business_key) VALUES (?, ?)",
            (user_id, business_key),
        )
        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_auth.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat: add UserManager.link_business() with idempotent INSERT OR IGNORE"
```

---

## Task 3: Google OAuth Web Flow Methods

**Files:**
- Modify: `core/google_auth.py`
- Modify: `skills/google_sheets_manager.py`
- Create: `tests/test_google_oauth_flow.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_google_oauth_flow.py
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from core.google_auth import GoogleWorkspaceAuth


def test_build_web_auth_url_returns_string():
    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?foo=bar", "state123")
    with patch("core.google_auth.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow
        url = GoogleWorkspaceAuth.build_web_auth_url(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost/callback",
            state="state123",
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    assert url.startswith("https://accounts.google.com")


def test_exchange_web_auth_code_returns_credentials():
    mock_creds = MagicMock()
    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    with patch("core.google_auth.Flow") as MockFlow:
        MockFlow.from_client_config.return_value = mock_flow
        result = GoogleWorkspaceAuth.exchange_web_auth_code(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost/callback",
            state="state123",
            code="auth_code_xyz",
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    mock_flow.fetch_token.assert_called_once_with(code="auth_code_xyz")
    assert result is mock_creds


def test_token_path_overrides_default():
    auth = GoogleWorkspaceAuth(token_path="/tmp/my_tokens.json")
    assert auth.oauth_token_path == "/tmp/my_tokens.json"


def test_from_token_path_sets_auth():
    from skills.google_sheets_manager import GoogleSheetsManager
    manager = GoogleSheetsManager.from_token_path("/tmp/biz_tokens.json")
    assert manager.auth.oauth_token_path == "/tmp/biz_tokens.json"
    assert manager._service is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_google_oauth_flow.py -v
```
Expected: FAIL — `AttributeError: type object 'GoogleWorkspaceAuth' has no attribute 'build_web_auth_url'`

- [ ] **Step 3: Add `token_path` param and two static methods to `core/google_auth.py`**

Change the `__init__` signature and the `oauth_token_path` line:

```python
# Replace this line in __init__:
#   self.oauth_token_path = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "credentials/google-token.json")
# With:
    def __init__(self, credentials_path: str | None = None, *, token_path: str | None = None) -> None:
        self.credentials_path = credentials_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self.oauth_client_path = os.getenv(
            "GOOGLE_OAUTH_CLIENT_SECRET_FILE",
            os.getenv("GOOGLE_OAUTH_CLIENT_FILE", "credentials/google-oauth-client.json"),
        )
        self.oauth_token_path = token_path or os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "credentials/google-token.json")
        self.subject = os.getenv("GOOGLE_WORKSPACE_USER")
        self._credentials = None
        self._services: dict = {}
```

Then add these two static methods at the end of the class (before `reset_service`):

```python
    @staticmethod
    def build_web_auth_url(
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        state: str,
        scopes: list[str],
    ) -> str:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=scopes,
            redirect_uri=redirect_uri,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url

    @staticmethod
    def exchange_web_auth_code(
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        state: str,
        code: str,
        scopes: list[str],
    ) -> "UserCredentials":
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=scopes,
            redirect_uri=redirect_uri,
            state=state,
        )
        flow.fetch_token(code=code)
        return flow.credentials
```

Also add `Flow` to the import at the top of `core/google_auth.py`:

```python
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
```

- [ ] **Step 4: Add `from_token_path()` classmethod to `skills/google_sheets_manager.py`**

Add this classmethod to `GoogleSheetsManager`, after `__init__`:

```python
    @classmethod
    def from_token_path(cls, token_path: str) -> "GoogleSheetsManager":
        """Build a GoogleSheetsManager authenticated with a per-business OAuth token file."""
        instance = cls.__new__(cls)
        instance.credentials_path = None
        instance.auth = GoogleWorkspaceAuth(token_path=token_path)
        instance._service = None
        return instance
```

Also ensure `GoogleWorkspaceAuth` is imported at the top of `skills/google_sheets_manager.py` — it already is via `from core.google_auth import GoogleWorkspaceAuth`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_google_oauth_flow.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Run full suite to check no regressions**

```bash
python -m pytest tests/ --ignore=tests/test_main_fixes.py --ignore=tests/test_web_app.py -q
```
Expected: same pass count as before + 4 new passes.

- [ ] **Step 7: Commit**

```bash
git add core/google_auth.py skills/google_sheets_manager.py tests/test_google_oauth_flow.py
git commit -m "feat: add web OAuth flow methods to GoogleWorkspaceAuth; add from_token_path to GoogleSheetsManager"
```

---

## Task 4: Create routes/onboarding.py

**Files:**
- Create: `routes/onboarding.py`

- [ ] **Step 1: Create the file**

```python
# routes/onboarding.py
"""Onboarding wizard endpoints: business registration and Google OAuth."""
from __future__ import annotations

import os
import secrets
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


@router.get("/onboarding")
def onboarding_page(request: Request) -> Any:
    # Only gate on login — JS handles step routing and the "already done" redirect.
    # Server must NOT redirect away here: Google OAuth callback returns to /onboarding?step=3
    # and that page-load must succeed even when the user already has a business.
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
            business_key, _, _ = agent.memory.create_business(
                payload.business_name.strip(), state=payload.state
            )
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
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
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
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
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
        pass  # Sheet creation is non-fatal; user can reconnect in Settings
    return RedirectResponse(url="/onboarding?step=3", status_code=302)
```

- [ ] **Step 2: Verify line count is under 300**

```bash
wc -l routes/onboarding.py
```
Expected: under 130 lines.

- [ ] **Step 3: Smoke-test import**

```bash
python -c "from routes.onboarding import router; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add routes/onboarding.py
git commit -m "feat: add routes/onboarding.py with business registration and Google OAuth endpoints"
```

---

## Task 5: Update routes/auth.py

**Files:**
- Modify: `routes/auth.py`

- [ ] **Step 1: Replace the `index` route**

Find and replace the entire `@router.get("/")` function:

```python
@router.get("/")
def index(request: Request) -> Response:
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    if not user_manager.get_user_businesses(user_id):
        return RedirectResponse(url="/onboarding", status_code=302)
    return FileResponse(UI_DIR / "index.html")
```

- [ ] **Step 2: Replace the `login_page` route**

Find and replace the entire `@router.get("/login")` function:

```python
@router.get("/login")
def login_page(request: Request) -> Response:
    user_id = request.session.get("user_id")
    if user_id:
        if user_manager.get_user_businesses(user_id):
            return RedirectResponse(url="/", status_code=302)
        return RedirectResponse(url="/onboarding", status_code=302)
    return FileResponse(UI_DIR / "login.html")
```

- [ ] **Step 3: Retire the `/setup` page and `/api/setup/create-owner`**

Replace the `setup_page` function:

```python
@router.get("/setup")
def setup_page() -> Response:
    raise HTTPException(status_code=404, detail="Not found.")
```

Replace the `setup_create_owner` function:

```python
@router.post("/api/setup/create-owner")
def setup_create_owner() -> Response:
    raise HTTPException(status_code=404, detail="Not found.")
```

- [ ] **Step 4: Add `GET /signup` page route and `POST /api/auth/signup`**

Add these two functions after `auth_me`:

```python
@router.get("/signup")
def signup_page(request: Request) -> Response:
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(UI_DIR / "signup.html")


@router.post("/api/auth/signup")
def auth_signup(payload: SignupRequest, request: Request) -> dict:
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    try:
        user = user_manager.create_user(
            payload.username.strip(), payload.email.strip(), payload.password, "owner"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session["user_id"] = user["id"]
    return {"ok": True, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}
```

- [ ] **Step 5: Add `SignupRequest` to the import block**

Find the existing import from `models.requests` and add `SignupRequest`:

```python
from models.requests import (
    BusinessSwitchRequest, CreateUserRequest, LoginRequest,
    ModelModeRequest, ProfileUpdateRequest, ProviderRequest, SignupRequest, UpdateUserRequest,
)
```

- [ ] **Step 6: Verify line count stays under 300**

```bash
wc -l routes/auth.py
```
Expected: under 250 lines.

- [ ] **Step 7: Smoke-test import**

```bash
python -c "from routes.auth import router; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add routes/auth.py
git commit -m "feat: add /signup route + POST /api/auth/signup; retire /setup; fix / redirect logic"
```

---

## Task 6: Register Onboarding Router in web_app.py

**Files:**
- Modify: `web_app.py`

- [ ] **Step 1: Add the onboarding router**

Open `web_app.py`. Find the block where routers are imported and included. Add two lines:

In the imports section, add:
```python
from routes.onboarding import router as onboarding_router
```

In the `app.include_router(...)` block, add:
```python
app.include_router(onboarding_router)
```

- [ ] **Step 2: Verify the app imports cleanly**

```bash
python -c "import web_app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add web_app.py
git commit -m "feat: register onboarding router in web_app.py"
```

---

## Task 7: Create ui/signup.html

**Files:**
- Create: `ui/signup.html`

- [ ] **Step 1: Create the file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>CPA-Agent — Create Account</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Outfit',sans-serif;background:#0f172a;display:flex;align-items:center;justify-content:center;min-height:100vh;color:#f1f5f9}
    .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:2.5rem;width:100%;max-width:420px}
    h1{font-size:1.5rem;font-weight:700;margin-bottom:.25rem}
    .subtitle{color:#94a3b8;font-size:.875rem;margin-bottom:2rem}
    label{display:block;font-size:.8rem;color:#94a3b8;margin-bottom:.4rem;font-weight:500;text-transform:uppercase;letter-spacing:.05em}
    input{width:100%;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:.65rem .9rem;color:#f1f5f9;font-size:.95rem;margin-bottom:1.25rem}
    input:focus{outline:none;border-color:#10b981}
    button{width:100%;background:#10b981;color:#fff;border:none;border-radius:8px;padding:.75rem;font-size:1rem;font-weight:600;cursor:pointer}
    button:hover{background:#059669}
    #error{color:#f87171;font-size:.85rem;margin-top:.75rem;text-align:center;min-height:1.2em}
    .alt-link{text-align:center;margin-top:1.25rem;font-size:.875rem;color:#94a3b8}
    .alt-link a{color:#10b981;text-decoration:none}
    .alt-link a:hover{text-decoration:underline}
  </style>
</head>
<body>
<div class="card">
  <h1>🧾 Create Account</h1>
  <p class="subtitle">Sign up to start managing your books</p>
  <form id="signup-form">
    <label for="username">Username</label>
    <input id="username" type="text" autocomplete="username" required/>
    <label for="email">Email</label>
    <input id="email" type="email" autocomplete="email" required/>
    <label for="password">Password (min 8 characters)</label>
    <input id="password" type="password" autocomplete="new-password" required minlength="8"/>
    <label for="confirm">Confirm Password</label>
    <input id="confirm" type="password" autocomplete="new-password" required minlength="8"/>
    <button type="submit">Create Account</button>
    <p id="error"></p>
  </form>
  <p class="alt-link">Already have an account? <a href="/login">Sign in</a></p>
</div>
<script>
document.getElementById('signup-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  var errEl = document.getElementById('error');
  errEl.textContent = '';
  var password = document.getElementById('password').value;
  var confirm  = document.getElementById('confirm').value;
  if (password !== confirm) { errEl.textContent = 'Passwords do not match.'; return; }
  try {
    var r = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        username: document.getElementById('username').value.trim(),
        email:    document.getElementById('email').value.trim(),
        password: password,
        confirm_password: confirm,
      })
    });
    if (r.ok) {
      window.location.href = '/onboarding';
    } else {
      var d = await r.json();
      errEl.textContent = d.detail || 'Signup failed.';
    }
  } catch(err) {
    errEl.textContent = 'Network error. Please try again.';
  }
});
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add ui/signup.html
git commit -m "feat: add ui/signup.html"
```

---

## Task 8: Update ui/login.html

**Files:**
- Modify: `ui/login.html`

- [ ] **Step 1: Add the Sign Up link**

In `ui/login.html`, find the closing `</div>` of the card (just before `</body>`) and add the following after the `<form>` block, still inside `.card`:

```html
  <p class="alt-link">Don't have an account? <a href="/signup">Sign up</a></p>
```

Also add the `.alt-link` CSS rule inside `<style>`:

```css
.alt-link{text-align:center;margin-top:1.25rem;font-size:.875rem;color:#94a3b8}
.alt-link a{color:#6366f1;text-decoration:none}
.alt-link a:hover{text-decoration:underline}
```

- [ ] **Step 2: Commit**

```bash
git add ui/login.html
git commit -m "feat: add Sign Up link to login page"
```

---

## Task 9: Create ui/onboarding.html

**Files:**
- Create: `ui/onboarding.html`

- [ ] **Step 1: Create the file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>CPA-Agent — Set Up Your Business</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Outfit',sans-serif;background:#0f172a;display:flex;align-items:center;justify-content:center;min-height:100vh;color:#f1f5f9;padding:1rem}
    .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:2.5rem;width:100%;max-width:480px}
    h1{font-size:1.4rem;font-weight:700;margin-bottom:.25rem}
    .subtitle{color:#94a3b8;font-size:.875rem;margin-bottom:1.5rem}
    .steps{display:flex;gap:.5rem;justify-content:center;margin-bottom:2rem}
    .step-dot{width:10px;height:10px;border-radius:50%;background:#334155;transition:background .3s}
    .step-dot.active{background:#10b981}
    label{display:block;font-size:.8rem;color:#94a3b8;margin-bottom:.4rem;font-weight:500;text-transform:uppercase;letter-spacing:.05em}
    input,select{width:100%;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:.65rem .9rem;color:#f1f5f9;font-size:.95rem;margin-bottom:1.25rem}
    input:focus,select:focus{outline:none;border-color:#10b981}
    select option{background:#1e293b}
    .btn{width:100%;border:none;border-radius:8px;padding:.75rem;font-size:1rem;font-weight:600;cursor:pointer;margin-bottom:.5rem}
    .btn-primary{background:#10b981;color:#fff}
    .btn-primary:hover{background:#059669}
    .btn-secondary{background:transparent;color:#94a3b8;border:1px solid #334155}
    .btn-secondary:hover{border-color:#94a3b8;color:#f1f5f9}
    #s1-error{color:#f87171;font-size:.85rem;margin-top:.5rem;text-align:center;min-height:1.2em}
    .step{display:none}
    .step.active{display:block}
    .google-box{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:1.25rem;margin-bottom:1.5rem;text-align:center}
    .google-box .icon{font-size:2rem;margin-bottom:.5rem}
    .google-box p{color:#94a3b8;font-size:.875rem;line-height:1.6}
    #google-error{color:#f87171;font-size:.85rem;margin-top:.5rem;text-align:center;min-height:1.2em}
    .done-icon{font-size:3rem;text-align:center;margin-bottom:1rem}
    .done-summary{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:1rem;margin-bottom:1.5rem;font-size:.875rem;line-height:1.7}
  </style>
</head>
<body>
<div class="card">
  <h1>🧾 Set Up Your Business</h1>
  <p class="subtitle" id="step-subtitle">Step 1 of 3 — Business Details</p>
  <div class="steps">
    <div class="step-dot active" id="dot-1"></div>
    <div class="step-dot" id="dot-2"></div>
    <div class="step-dot" id="dot-3"></div>
  </div>

  <!-- Step 1 -->
  <div class="step active" id="step-1">
    <form id="business-form">
      <label for="business_name">Business Name *</label>
      <input id="business_name" type="text" required placeholder="Acme LLC"/>
      <label for="legal_structure">Business Type *</label>
      <select id="legal_structure" required>
        <option value="">Select…</option>
        <option value="single_member_llc">Single-Member LLC</option>
        <option value="multi_member_llc">Multi-Member LLC</option>
        <option value="s_corp">S-Corp</option>
        <option value="c_corp">C-Corp</option>
        <option value="sole_proprietor">Sole Proprietor</option>
        <option value="partnership">Partnership</option>
      </select>
      <label for="industry">Industry *</label>
      <select id="industry" required>
        <option value="">Select…</option>
        <option value="e_commerce">E-Commerce</option>
        <option value="professional_services">Professional Services</option>
        <option value="retail">Retail</option>
        <option value="import_export">Import / Export</option>
        <option value="construction">Construction</option>
        <option value="healthcare">Healthcare</option>
        <option value="content_creator">Content Creator</option>
        <option value="manufacturing">Manufacturing</option>
        <option value="other">Other</option>
      </select>
      <label for="ein">EIN (optional)</label>
      <input id="ein" type="text" placeholder="XX-XXXXXXX" maxlength="10"/>
      <label for="state">State</label>
      <select id="state">
        <option value="">Select…</option>
        <option>AL</option><option>AK</option><option>AZ</option><option>AR</option>
        <option>CA</option><option>CO</option><option>CT</option><option>DE</option>
        <option>DC</option><option>FL</option><option>GA</option><option>HI</option>
        <option>ID</option><option>IL</option><option>IN</option><option>IA</option>
        <option>KS</option><option>KY</option><option>LA</option><option>ME</option>
        <option>MD</option><option>MA</option><option>MI</option><option>MN</option>
        <option>MS</option><option>MO</option><option>MT</option><option>NE</option>
        <option>NV</option><option>NH</option><option>NJ</option><option>NM</option>
        <option>NY</option><option>NC</option><option>ND</option><option>OH</option>
        <option>OK</option><option>OR</option><option>PA</option><option>RI</option>
        <option>SC</option><option>SD</option><option>TN</option><option>TX</option>
        <option>UT</option><option>VT</option><option>VA</option><option>WA</option>
        <option>WV</option><option>WI</option><option>WY</option>
      </select>
      <label for="accounting_basis">Accounting Basis</label>
      <select id="accounting_basis">
        <option value="cash">Cash</option>
        <option value="accrual">Accrual</option>
      </select>
      <button type="submit" class="btn btn-primary">Continue →</button>
      <p id="s1-error"></p>
    </form>
  </div>

  <!-- Step 2 -->
  <div class="step" id="step-2">
    <div class="google-box">
      <div class="icon">📊</div>
      <p>Connect your Google account to create a dedicated spreadsheet for your business in your own Google Drive.</p>
    </div>
    <button id="btn-google" class="btn btn-primary">Connect Google Account →</button>
    <button id="btn-skip" class="btn btn-secondary">Skip for now — connect later in Settings</button>
    <p id="google-error"></p>
  </div>

  <!-- Step 3 -->
  <div class="step" id="step-3">
    <div class="done-icon">✅</div>
    <div class="done-summary" id="done-summary">Your business has been registered.</div>
    <button id="btn-dashboard" class="btn btn-primary">Go to Dashboard →</button>
  </div>
</div>

<script>
var _googleConnected = false;

function setStep(n) {
  [1,2,3].forEach(function(i) {
    document.getElementById('step-' + i).classList.toggle('active', i === n);
    document.getElementById('dot-' + i).classList.toggle('active', i === n);
  });
  var labels = {1:'Step 1 of 3 — Business Details', 2:'Step 2 of 3 — Connect Google', 3:'Step 3 of 3 — All Done!'};
  document.getElementById('step-subtitle').textContent = labels[n] || '';
}

function renderDoneSummary() {
  var msg = _googleConnected
    ? '✅ Google Sheets connected — your ledger spreadsheet is ready.'
    : '⚠️ Google Sheets not connected. You can connect later in Settings.';
  document.getElementById('done-summary').innerHTML =
    '<p>Your business has been registered.</p><p style="margin-top:.5rem;color:#94a3b8">' + msg + '</p>';
}

// On load: read URL params, then fetch status and route to correct step.
// ?step=N always wins (Google OAuth callback lands here with ?step=3).
// Otherwise: if already onboarded → dashboard; else stay on step 1.
(function init() {
  var params = new URLSearchParams(window.location.search);
  var step = parseInt(params.get('step'), 10);
  var err  = params.get('error');
  if (err) {
    document.getElementById('google-error').textContent =
      'Google connection failed or was denied. You can try again or skip.';
  }
  fetch('/api/onboarding/status')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      _googleConnected = !!d.google_connected;
      if (step >= 1 && step <= 3) { setStep(step); renderDoneSummary(); return; }
      if (d.onboarding_complete) { window.location.href = '/'; return; }
      // else: new user, stay on step 1
    })
    .catch(function() {});
})();

// Step 1 form submit
document.getElementById('business-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  var errEl = document.getElementById('s1-error');
  errEl.textContent = '';
  var payload = {
    business_name:   document.getElementById('business_name').value.trim(),
    legal_structure: document.getElementById('legal_structure').value,
    industry:        document.getElementById('industry').value,
    ein:             document.getElementById('ein').value.trim(),
    state:           document.getElementById('state').value,
    accounting_basis:document.getElementById('accounting_basis').value,
  };
  try {
    var r = await fetch('/api/onboarding/business', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload),
    });
    var d = await r.json();
    if (r.ok) { setStep(2); } else { errEl.textContent = d.detail || 'Failed to save business.'; }
  } catch(_) { errEl.textContent = 'Network error.'; }
});

// Step 2: Connect Google
document.getElementById('btn-google').addEventListener('click', async function() {
  var errEl = document.getElementById('google-error');
  errEl.textContent = '';
  try {
    var r = await fetch('/api/onboarding/google-auth');
    var d = await r.json();
    if (r.ok && d.auth_url) { window.location.href = d.auth_url; }
    else { errEl.textContent = d.detail || 'Could not start Google sign-in.'; }
  } catch(_) { errEl.textContent = 'Network error.'; }
});

// Step 2: Skip
document.getElementById('btn-skip').addEventListener('click', function() {
  _googleConnected = false;
  setStep(3);
  renderDoneSummary();
});

// Step 3: Dashboard
document.getElementById('btn-dashboard').addEventListener('click', function() {
  window.location.href = '/';
});
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add ui/onboarding.html
git commit -m "feat: add ui/onboarding.html 3-step wizard"
```

---

## Task 10: Clean Up and Final Verification

**Files:**
- Delete: `ui/setup.html`

- [ ] **Step 1: Delete ui/setup.html**

```bash
git rm ui/setup.html
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/ --ignore=tests/test_main_fixes.py --ignore=tests/test_web_app.py -q
```
Expected: all previous passes + new passes from Tasks 1–3, no regressions.

- [ ] **Step 3: Smoke-test full app startup**

```bash
python -c "import web_app; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete signup + onboarding flow; retire /setup"
```

- [ ] **Step 5: Push**

```bash
git push
```
