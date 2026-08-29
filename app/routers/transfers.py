"""
Transfer API router.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import TransferExplainResponse, TransferRequest, TransferResponse
from app.services import (
    explain_transfer,
    execute_transfer,
    get_existing_transfer,
    _compute_balance,
)

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


@router.get("/{transfer_id}/explain", response_model=TransferExplainResponse)
def explain(
    transfer_id: str,
    db: Session = Depends(get_db),
):
    """
    Transaction Explainability Engine.

    Returns a complete human-readable explanation of a transfer:
    who paid whom, how much, the resulting balance changes, both ledger
    entries with their hash-chain links, and a narrative paragraph.

    Designed for the "Explain" button on the Transactions page — a judge
    clicks any past transfer and sees exactly what the ledger recorded.
    """
    try:
        report = explain_transfer(db, transfer_id)  # type: ignore[arg-type]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return TransferExplainResponse(**report)
