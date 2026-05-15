"""Pydantic request models for the CPA-Agent API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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


class BalanceSheetRequest(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class CashFlowRequest(BaseModel):
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class BudgetRequest(BaseModel):
    category: str
    amount: float
    period: str


class ReconcileResolveRequest(BaseModel):
    date: str
    description: str
    amount: float
    action: str


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
