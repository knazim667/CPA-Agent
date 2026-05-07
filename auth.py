from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext

# Compatibility shim: passlib 1.7.4 reads bcrypt.__about__.__version__ which
# was removed in bcrypt 4.1. This shim prevents an AttributeError on import.
import bcrypt as _bcrypt
if not hasattr(_bcrypt, "__about__"):
    _bcrypt.__about__ = type("_About", (), {"__version__": _bcrypt.__version__})()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('owner','bookkeeper','employee')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_businesses (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    business_key TEXT NOT NULL,
                    PRIMARY KEY (user_id, business_key)
                )
            """)
            conn.commit()

    def is_empty(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return count == 0

    def _row_to_user(self, row: tuple, include_hash: bool = False) -> dict[str, Any]:
        user = {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "role": row[4],
            "is_active": bool(row[5]),
            "created_at": row[6],
        }
        if include_hash:
            user["password_hash"] = row[3]
        return user

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: str,
        business_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        password_hash = _pwd_context.hash(password)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, email, password_hash, role),
            )
            user_id = cursor.lastrowid
            if role != "owner" and business_keys:
                for key in business_keys:
                    conn.execute(
                        "INSERT INTO user_businesses (user_id, business_key) VALUES (?, ?)",
                        (user_id, key),
                    )
            conn.commit()
        return self.get_user_by_id(user_id)

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, username, email, password_hash, role, is_active, created_at "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, username, email, password_hash, role, is_active, created_at "
                "FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return self._row_to_user(row, include_hash=True) if row else None

    def verify_password(self, username: str, password: str) -> Optional[dict[str, Any]]:
        user = self.get_user_by_username(username)
        if not user or not user["is_active"]:
            return None
        if not _pwd_context.verify(password, user["password_hash"]):
            return None
        user.pop("password_hash", None)
        return user

    def list_users(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, username, email, password_hash, role, is_active, created_at "
                "FROM users ORDER BY id"
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def update_user(
        self,
        user_id: int,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        business_keys: list[str] | None = None,
    ) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            if role is not None:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            if is_active is not None:
                conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))
            if business_keys is not None:
                conn.execute("DELETE FROM user_businesses WHERE user_id = ?", (user_id,))
                for key in business_keys:
                    conn.execute(
                        "INSERT INTO user_businesses (user_id, business_key) VALUES (?, ?)",
                        (user_id, key),
                    )
            conn.commit()
        return self.get_user_by_id(user_id)

    def get_user_businesses(self, user_id: int) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT business_key FROM user_businesses WHERE user_id = ?", (user_id,)
            ).fetchall()
        return [r[0] for r in rows]

    def can_access_business(self, user: dict[str, Any], business_key: str) -> bool:
        if user["role"] == "owner":
            return True
        return business_key in self.get_user_businesses(user["id"])


# ---------------------------------------------------------------------------
# FastAPI dependency helpers — imported by web_app.py
# ---------------------------------------------------------------------------

def get_current_user(request: Request) -> dict[str, Any]:
    """Raises 401 if no valid session."""
    from web_app import user_manager  # late import avoids circular dependency
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = user_manager.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_owner(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


def require_owner_or_bookkeeper(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if user["role"] not in ("owner", "bookkeeper"):
        raise HTTPException(status_code=403, detail="Owner or bookkeeper access required")
    return user
