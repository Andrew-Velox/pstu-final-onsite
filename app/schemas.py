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
