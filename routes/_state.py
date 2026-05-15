"""Shared runtime state — agent, locks, draft store — for all route modules."""
from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any

from auth import UserManager
from main import CPAAgent
from skills import DocumentProcessor

ROOT_DIR = Path(__file__).resolve().parent.parent
UI_DIR = ROOT_DIR / "ui"
UPLOAD_DIR = ROOT_DIR / "uploads"

agent = CPAAgent()
agent.memory.migrate_business_profiles()
user_manager = UserManager(ROOT_DIR / "memory" / "users.db")
document_processor = DocumentProcessor(UPLOAD_DIR)
agent_lock = Lock()
pending_document_drafts: dict[str, dict[str, Any]] = {}

_DRAFT_TTL_SECONDS = 3600
_DRAFT_MAX_ENTRIES = 100


def _evict_stale_drafts() -> None:
    now = time.time()
    stale = [
        k for k, v in pending_document_drafts.items()
        if now - v.get("created_at", 0) > _DRAFT_TTL_SECONDS
    ]
    for k in stale:
        pending_document_drafts.pop(k, None)
    if len(pending_document_drafts) > _DRAFT_MAX_ENTRIES:
        oldest = sorted(pending_document_drafts.items(), key=lambda x: x[1].get("created_at", 0))
        for k, _ in oldest[: len(pending_document_drafts) - _DRAFT_MAX_ENTRIES]:
            pending_document_drafts.pop(k, None)
