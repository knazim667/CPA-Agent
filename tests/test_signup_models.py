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
