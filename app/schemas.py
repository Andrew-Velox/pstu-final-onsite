"""
Pydantic schemas for request/response serialization.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


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
