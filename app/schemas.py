"""
Pydantic schemas for request/response serialization.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ─── User ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    """POST /users request body — registration."""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="User's email address. Must contain an '@'.",
    )


class UserResponse(BaseModel):
    """Response body for user creation / lookup."""
    id: UUID
    name: str
    email: str
    balance: Decimal = Field(
        description="User's current ledger-derived balance",
    )
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── System health ────────────────────────────────────────────────────────────

class HealthCheckResponse(BaseModel):
    """GET /system/health-check response.

    The ledger is correct iff ``net_balance == 0`` — every credit in the
    system is exactly offset by a debit, so the absolute sum of all
    ledger amounts must come back to zero.
    """
    total_credits: Decimal
    total_debits: Decimal
    net_balance: Decimal
    ledger_is_balanced: bool
    user_count: int
    transfer_count: int


# ─── Transfer ─────────────────────────────────────────────────────────────────

class TransferRequest(BaseModel):
    """POST /transfers request body."""
    sender_id: UUID
    receiver_id: UUID
    amount: Decimal = Field(..., gt=0, description="Must be > 0")
    idempotency_key: str = Field(
        ..., min_length=1, max_length=255,
        description="Unique key to prevent duplicate transfers",
    )


class TransferResponse(BaseModel):
    """POST /transfers response body."""
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    amount: Decimal
    status: str
    idempotency_key: str
    created_at: datetime
    sender_balance: Decimal = Field(
        description="Sender's updated balance after the transfer",
    )

    model_config = {"from_attributes": True}


# ─── Money Request ────────────────────────────────────────────────────────────

class MoneyRequestCreate(BaseModel):
    """POST /requests request body."""
    requester_id: UUID
    target_id: UUID
    amount: Decimal = Field(..., gt=0, description="Must be > 0")


class MoneyRequestResponse(BaseModel):
    """Response body for money-request endpoints."""
    id: UUID
    requester_id: UUID
    target_id: UUID
    amount: Decimal
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApproveDeclineBody(BaseModel):
    """Body for approve/decline actions — simulates auth via user_id."""
    user_id: UUID


# ─── Transaction History ──────────────────────────────────────────────────────

class TransactionItem(BaseModel):
    """
    A single entry in a user's transaction history.

    Shaped for easy frontend rendering — flat, with the counterparty name
    resolved server-side so the frontend doesn't need to look it up.
    """
    transfer_id: UUID
    direction: str = Field(
        description="'sent' (debit) or 'received' (credit)",
    )
    amount: Decimal
    counterparty_id: UUID
    counterparty_name: str
    timestamp: datetime


class TransactionListResponse(BaseModel):
    """Paginated transaction history."""
    items: list[TransactionItem]
    total: int
    limit: int
    offset: int


class BalanceResponse(BaseModel):
    """GET /users/{user_id}/balance response."""
    user_id: UUID
    balance: Decimal
