"""CPA-Agent web application — thin FastAPI app factory."""
from __future__ import annotations

import os
import warnings

from dotenv import load_dotenv

load_dotenv()

if os.environ.get("SECRET_KEY", "dev-insecure-key") == "dev-insecure-key":
    warnings.warn(
        "SECRET_KEY is using the insecure default. Set a real 64-char hex value in .env before deploying.",
        stacklevel=1,
    )

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from routes._state import UI_DIR
from routes.auth import router as auth_router
from routes.onboarding import router as onboarding_router
from routes.transactions import router as transactions_router
from routes.reports import router as reports_router
from routes.recurring import router as recurring_router
from routes.budget import router as budget_router
from routes.ar_ap import router as ar_ap_router
from routes.tax import router as tax_router
from routes.reconcile import router as reconcile_router

app = FastAPI(title="CPA-Agent UI")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-insecure-key"),
    session_cookie="cpa_session",
    max_age=86400,
    https_only=False,
    same_site="lax",
)

app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(transactions_router)
app.include_router(reports_router)
app.include_router(recurring_router)
app.include_router(budget_router)
app.include_router(ar_ap_router)
app.include_router(tax_router)
app.include_router(reconcile_router)


def main() -> int:
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
