# Signup & Onboarding Design

> **For agentic workers:** Use superpowers:writing-plans to implement this spec.

**Goal:** Replace the one-time `/setup` page with a full public signup + 3-step onboarding wizard, with Google OAuth2 per business so every business gets its own Google Sheet.

**Approach:** Extend `/signup` as the universal account-creation entry point (works for first user and all subsequent users). After signup + auto-login, redirect to `/onboarding` wizard. The `onboarding_complete` flag in the business profile gates the main dashboard.

---

## 1. User Flow & Routing

```
GET /
 ├─ not logged in               → redirect /login
 ├─ onboarding_complete == false → redirect /onboarding
 └─ logged in + onboarded       → serve index.html

GET /login
 ├─ already logged in + onboarded → redirect /
 └─ show login.html (with "Sign up" link)

GET /signup            ← NEW
 ├─ already logged in → redirect /
 └─ show signup.html

GET /onboarding        ← NEW
 ├─ not logged in      → redirect /login
 ├─ already onboarded  → redirect /
 └─ show onboarding.html

GET /setup             ← RETIRED → 404
POST /api/setup/create-owner  ← RETIRED → 404
```

**Post-signup chain:** `/signup` → auto-login → `/onboarding` → (complete) → `/`

**Return-visit behaviour:** If a user logs in and `onboarding_complete` is still false (they dropped off mid-wizard), `GET /` redirects them back to `/onboarding`. The wizard reads `/api/onboarding/status` on load to resume at the correct step.

---

## 2. Pages

### `ui/signup.html`
Dark-card style matching existing login/setup pages (Outfit font, `#0f172a` background, `#1e293b` card).

Fields:
- Username
- Email
- Password (min 8 chars)
- Confirm Password
- "Create Account" button → `POST /api/auth/signup`
- Footer link: "Already have an account? Sign in" → `/login`

On success: auto-logged-in, redirect to `/onboarding`.

### `ui/login.html` (modified)
Add one line below the submit button:
```
Don't have an account? Sign up  →  /signup
```

### `ui/onboarding.html`
Single HTML page. JS drives step transitions — no page reloads between steps. Step indicator dots at top (`● ○ ○`, `● ● ○`, `● ● ●`).

**Step 1 — Business Details**
Fields: Business Name (required), Business Type (select: LLC / S-Corp / Sole Proprietor / Partnership / C-Corp), Industry (select: e-commerce / professional services / retail / import-export / construction / healthcare / content creator / manufacturing / other), EIN (optional, formatted XX-XXXXXXX), State (select, all 50 + DC), Accounting Basis (select: Cash / Accrual).
Button: "Continue →" → `POST /api/onboarding/business` → on success, advance to Step 2.

**Step 2 — Connect Google Account**
Explains that a dedicated Google Sheet will be created in the user's own Drive.
Buttons:
- "Connect Google →" → `GET /api/onboarding/google-auth` → follow redirect to Google OAuth
- "Skip for now — connect later in Settings" → marks step skipped, redirects to `/onboarding?step=3`

**Step 3 — Done**
Shows confirmation: business name, and whether Google Sheets was connected or skipped.
Button: "Go to Dashboard →" → `/`

---

## 3. API Endpoints

All new endpoints live in `routes/auth.py` (auth + onboarding are tightly coupled).

### `POST /api/auth/signup`
**Auth:** none  
**Body:** `SignupRequest` — `{ username, email, password, confirm_password }`  
**Logic:**
1. Validate `password == confirm_password` and `len(password) >= 8`
2. `user_manager.create_user(username, email, password, role="owner")`
3. Set `request.session["user_id"]`
4. Return `{ ok: true, user: { id, username, role } }`

**Errors:** 400 if username/email already taken, 400 if password mismatch or too short.

### `POST /api/onboarding/business`
**Auth:** session required  
**Body:** `OnboardingBusinessRequest` — `{ business_name, legal_structure, industry, ein, state, accounting_basis }`  
**Logic:**
1. `memory.create_business(business_name, state=state)`
2. `memory.update_business_profile(key, { legal_structure, industry, ein, accounting_basis, onboarding_complete: True })`
3. `user_manager.link_business(user_id, business_key)`
4. Return `{ ok: true, business_key }`

### `GET /api/onboarding/google-auth`
**Auth:** session required  
**Logic:** Build Google OAuth2 URL with scopes `spreadsheets` + `drive.file`. Store CSRF `state` token in session. Return `{ auth_url }`. Frontend redirects to `auth_url`.

### `GET /api/onboarding/google-callback`
**Auth:** session (state param validates CSRF)  
**Query:** `?code=…&state=…`  
**Logic:**
1. Validate `state` against session
2. Exchange `code` for `{ access_token, refresh_token, … }`
3. Write tokens to `memory/long_term/{business_key}/google_tokens.json`
4. Call `GoogleSheetsManager.create_spreadsheet(business_name)` using new OAuth credentials
5. Save `google_sheet_id` to business profile
6. Redirect to `/onboarding?step=3`

### `GET /api/onboarding/status`
**Auth:** session required  
**Returns:** `{ onboarding_complete: bool, google_connected: bool, business_key: str | null }`  
Used by `onboarding.html` on load to resume at the correct step.

### Retired endpoints
- `GET /setup` → 404
- `POST /api/setup/create-owner` → 404

---

## 4. Google OAuth Integration

**One-time Google Cloud setup (developer task):**
1. Create OAuth 2.0 Client ID (Web Application) in Google Cloud Console
2. Enable Google Sheets API and Google Drive API
3. Add authorized redirect URI: `http://localhost:{PORT}/api/onboarding/google-callback`
4. Add to `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=...
   GOOGLE_OAUTH_CLIENT_SECRET=...
   ```

**Token storage per business:**  
`memory/long_term/{business_key}/google_tokens.json`
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file"
  ]
}
```

**`core/google_auth.py` change:**  
Add a second credential path: if `google_tokens.json` exists for the current business, build a `google.oauth2.credentials.Credentials` object from stored tokens instead of loading a service account file. `GoogleSheetsManager` is unchanged — it still calls `self.auth.build_service("sheets", "v4")`.

**Token refresh:**  
`google-auth-oauthlib` handles refresh automatically via the `Credentials` object. If the access token is expired, it uses the refresh token transparently.

**New dependency:** `google-auth-oauthlib` (add to `requirements.txt`).

---

## 5. Data Model Changes

### `models/requests.py` — two new models
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

### `auth.py` — `UserManager`
Add `link_business(user_id: int, business_key: str) -> None` — inserts into `user_businesses` table (already exists in schema).

### `memory_store.py` / `PROFILE_DEFAULTS`
No change needed — `onboarding_complete: False` already exists.

---

## 6. Files Created / Modified

| File | Action |
|------|--------|
| `ui/signup.html` | Create |
| `ui/onboarding.html` | Create |
| `ui/login.html` | Modify — add Sign Up link |
| `routes/auth.py` | Modify — add 5 new endpoints, retire `/setup` |
| `models/requests.py` | Modify — add 2 new request models |
| `auth.py` | Modify — add `link_business()` to `UserManager` |
| `core/google_auth.py` | Modify — add OAuth2 token credential path |
| `requirements.txt` | Modify — add `google-auth-oauthlib` |
| `ui/setup.html` | Delete |

---

## 7. Error & Edge Cases

- **Duplicate signup:** `create_user` raises on unique constraint; endpoint returns 400 with clear message.
- **Google OAuth denied:** If user denies consent, Google redirects back with `error=access_denied`; callback catches this and redirects to `/onboarding?step=2&error=denied`.
- **Dropped onboarding:** User creates account but closes browser before completing Step 1. On next login, `GET /` sees `onboarding_complete=False` and redirects to `/onboarding`. Wizard calls `/api/onboarding/status` to check which step to resume.
- **No Google credentials in env:** If `GOOGLE_OAUTH_CLIENT_ID` is not set, the "Connect Google" button shows a warning; skip remains available.
- **Token expiry:** `google-auth-oauthlib` refreshes automatically. If refresh fails (revoked), Google connection shows as disconnected in Settings; user can re-connect.
