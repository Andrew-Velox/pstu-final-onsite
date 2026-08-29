"""
Transfer API router.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import TransferRequest, TransferResponse
from app.services import execute_transfer, get_existing_transfer, _compute_balance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransferResponse, status_code=201)
def create_transfer(
    body: TransferRequest,
    db: Session = Depends(get_db),
):
    """
    Execute a money transfer between two users.

    • Idempotent — retrying with the same ``idempotency_key`` returns
      the original result without re-processing.
    • Concurrency-safe — uses SELECT … FOR UPDATE with consistent lock
      ordering to prevent deadlocks and race conditions.
    • Atomic — the Transfer + two LedgerEntry rows are committed in a
      single transaction; any failure rolls everything back.
    """

    # ── Idempotency check (before any locks) ──────────────────────────────
    existing = get_existing_transfer(db, body.idempotency_key)
    if existing is not None:
        sender_balance = _compute_balance(db, existing.sender_id)
        return TransferResponse(
            id=existing.id,
            sender_id=existing.sender_id,
            receiver_id=existing.receiver_id,
            amount=existing.amount,
            status=existing.status.value,
            idempotency_key=existing.idempotency_key,
            created_at=existing.created_at,
            sender_balance=sender_balance,
        )

    # ── Execute inside a transaction ──────────────────────────────────────
    try:
        transfer, sender_balance = execute_transfer(
            db=db,
            sender_id=body.sender_id,
            receiver_id=body.receiver_id,
            amount=body.amount,
            idempotency_key=body.idempotency_key,
        )
        db.commit()
        db.refresh(transfer)

        return TransferResponse(
            id=transfer.id,
            sender_id=transfer.sender_id,
            receiver_id=transfer.receiver_id,
            amount=transfer.amount,
            status=transfer.status.value,
            idempotency_key=transfer.idempotency_key,
            created_at=transfer.created_at,
            sender_balance=sender_balance,
        )

    except ValueError as exc:
        db.rollback()
        logger.warning("Transfer rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:
        db.rollback()
        logger.exception("Unexpected error during transfer")
        raise HTTPException(status_code=500, detail="Internal server error")
