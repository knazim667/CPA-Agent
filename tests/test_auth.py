from __future__ import annotations
import sqlite3
import tempfile
from pathlib import Path
import pytest
from auth import UserManager


@pytest.fixture()
def um(tmp_path):
    return UserManager(tmp_path / "users.db")


def test_is_empty_on_new_db(um):
    assert um.is_empty() is True


def test_create_and_verify_owner(um):
    user = um.create_user("alice", "alice@example.com", "secret123", "owner")
    assert user["username"] == "alice"
    assert user["role"] == "owner"
    verified = um.verify_password("alice", "secret123")
    assert verified is not None
    assert verified["id"] == user["id"]


def test_wrong_password_returns_none(um):
    um.create_user("bob", "bob@example.com", "correct", "bookkeeper")
    assert um.verify_password("bob", "wrong") is None


def test_unknown_user_returns_none(um):
    assert um.verify_password("nobody", "pass") is None


def test_list_users(um):
    um.create_user("u1", "u1@example.com", "p", "owner")
    um.create_user("u2", "u2@example.com", "p", "employee")
    users = um.list_users()
    assert len(users) == 2
    assert {u["username"] for u in users} == {"u1", "u2"}


def test_update_role(um):
    user = um.create_user("carol", "carol@example.com", "p", "employee")
    updated = um.update_user(user["id"], role="bookkeeper")
    assert updated["role"] == "bookkeeper"


def test_deactivate_user(um):
    user = um.create_user("dave", "dave@example.com", "p", "employee")
    um.update_user(user["id"], is_active=False)
    assert um.verify_password("dave", "p") is None


def test_owner_can_access_any_business(um):
    user = um.create_user("owner1", "o@example.com", "p", "owner")
    assert um.can_access_business(user, "nazam_llc") is True
    assert um.can_access_business(user, "any_other_biz") is True


def test_bookkeeper_limited_to_assigned_businesses(um):
    user = um.create_user("bk1", "bk@example.com", "p", "bookkeeper",
                          business_keys=["nazam_llc"])
    assert um.can_access_business(user, "nazam_llc") is True
    assert um.can_access_business(user, "other_biz") is False


def test_duplicate_username_raises(um):
    um.create_user("dup", "dup@example.com", "p", "owner")
    with pytest.raises(Exception):
        um.create_user("dup", "dup2@example.com", "p", "employee")
