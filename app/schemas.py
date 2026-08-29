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
    ledger amounts must come back to zero.  The ``hash_chain_valid`` flag
    additionally proves that no entry has been tampered with.
    """
    total_credits: Decimal
    total_debits: Decimal
    net_balance: Decimal
    ledger_is_balanced: bool
    user_count: int
    transfer_count: int
    hash_chain_valid: bool
    hash_chain_entries_checked: int
    hash_chain_broken_at: str | None = None


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


# ─── Transaction Explainability Engine ────────────────────────────────────────

class LedgerEntryExplain(BaseModel):
    """One of the two ledger rows produced by a transfer, with hash-chain info."""
    id: UUID
    user_id: UUID
    user_name: str
    entry_type: str
    amount: Decimal
    created_at: datetime
    prev_hash: str
    entry_hash: str


class TransferExplainResponse(BaseModel):
    """
    GET /transfers/{id}/explain — a human-readable "explainability report"
    for a single transfer.

    Includes both ledger entries (debit + credit), the resulting balance
    changes for each party, and a hash-chain proof so a judge can see
    that the transfer is real, complete, and tamper-evident.
    """
    transfer_id: UUID
    sender_id: UUID
    sender_name: str
    receiver_id: UUID
    receiver_name: str
    amount: Decimal
    status: str
    idempotency_key: str
    created_at: datetime

    sender_balance_before: Decimal
    sender_balance_after: Decimal
    receiver_balance_before: Decimal
    receiver_balance_after: Decimal

    entries: list[LedgerEntryExplain]
    narrative: str = Field(
        description="One-paragraph human-readable explanation",
    )
    chain_position: int = Field(
        description="Position of this transfer's entries in the global chain",
    )


# ─── Money Movement Recovery Center ───────────────────────────────────────────

class RecoverySummary(BaseModel):
    """GET /recovery/summary — overview of stuck / replayable transfers."""
    total_transfers: int
    completed: int
    failed: int
    replayable: int
    pending_requests: int


class ReplayImpact(BaseModel):
    """Effect a replay *would* have, computed without persisting anything."""
    sender_balance_after: Decimal
    receiver_balance_after: Decimal
    sender_has_sufficient_funds: bool
    note: str


class ReplayRequest(BaseModel):
    """POST /recovery/replay body."""
    transfer_id: UUID


class ReplayResponse(BaseModel):
    """POST /recovery/replay response."""
    replayed: bool
    transfer_id: UUID
    note: str
    sender_balance: Decimal | None = None
