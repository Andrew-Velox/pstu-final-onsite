"""
Money-request API router.

Implements the request-money flow:
  • POST   /requests              — create a new money request (pending)
  • POST   /requests/{id}/approve — approve a pending request → executes transfer
  • POST   /requests/{id}/decline — decline a pending request
  • GET    /requests              — list pending requests for a user
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MoneyRequest, MoneyRequestStatus
from app.schemas import (
    ApproveDeclineBody,
    MoneyRequestCreate,
    MoneyRequestResponse,
)
from app.services import execute_transfer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/requests", tags=["money-requests"])


@router.post("", response_model=MoneyRequestResponse, status_code=201)
def create_money_request(
    body: MoneyRequestCreate,
    db: Session = Depends(get_db),
):
    """
    Create a money request.

    The *requester* is the person asking to receive money.
    The *target* is the person being asked to pay.
    """
    if body.requester_id == body.target_id:
        raise HTTPException(
            status_code=400,
            detail="Requester and target must be different users",
        )

    money_request = MoneyRequest(
        requester_id=body.requester_id,
        target_id=body.target_id,
        amount=body.amount,
        status=MoneyRequestStatus.pending,
    )
    db.add(money_request)
    db.commit()
    db.refresh(money_request)

    return MoneyRequestResponse(
        id=money_request.id,
        requester_id=money_request.requester_id,
        target_id=money_request.target_id,
        amount=money_request.amount,
        status=money_request.status.value,
        created_at=money_request.created_at,
    )


@router.post("/{request_id}/approve", response_model=MoneyRequestResponse)
def approve_money_request(
    request_id: UUID,
    body: ApproveDeclineBody,
    db: Session = Depends(get_db),
):
    """
    Approve a pending money request.

    Only the *target* (the person being asked to pay) can approve.
    On approval, a transfer is executed in the **same transaction**:
      sender = target_id, receiver = requester_id.

    A deterministic idempotency key ``request-{request_id}`` ensures
    retried approvals never double-execute the transfer.
    """
    money_request = db.query(MoneyRequest).filter(MoneyRequest.id == request_id).first()
    if money_request is None:
        raise HTTPException(status_code=404, detail="Money request not found")

    # ── Authorization: only the target can approve ────────────────────────
    if body.user_id != money_request.target_id:
        raise HTTPException(
            status_code=403,
            detail="Only the target user can approve this request",
        )

    # ── Prevent double-processing ─────────────────────────────────────────
    if money_request.status != MoneyRequestStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Request already {money_request.status.value}",
        )

    # ── Execute the transfer in the same transaction ──────────────────────
    idempotency_key = f"request-{request_id}"

    try:
        transfer, _ = execute_transfer(
            db=db,
            sender_id=money_request.target_id,      # target pays
            receiver_id=money_request.requester_id,  # requester receives
            amount=money_request.amount,
            idempotency_key=idempotency_key,
        )

        # Update status in the same transaction
        money_request.status = MoneyRequestStatus.approved
        db.commit()
        db.refresh(money_request)

        return MoneyRequestResponse(
            id=money_request.id,
            requester_id=money_request.requester_id,
            target_id=money_request.target_id,
            amount=money_request.amount,
            status=money_request.status.value,
            created_at=money_request.created_at,
        )

    except ValueError as exc:
        db.rollback()
        logger.warning("Money request approval rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:
        db.rollback()
        logger.exception("Unexpected error approving money request")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{request_id}/decline", response_model=MoneyRequestResponse)
def decline_money_request(
    request_id: UUID,
    body: ApproveDeclineBody,
    db: Session = Depends(get_db),
):
    """
    Decline a pending money request.

    Only the *target* (the person being asked to pay) can decline.
    No transfer or ledger entries are created.
    """
    money_request = db.query(MoneyRequest).filter(MoneyRequest.id == request_id).first()
    if money_request is None:
        raise HTTPException(status_code=404, detail="Money request not found")

    # ── Authorization: only the target can decline ────────────────────────
    if body.user_id != money_request.target_id:
        raise HTTPException(
            status_code=403,
            detail="Only the target user can decline this request",
        )

    # ── Prevent double-processing ─────────────────────────────────────────
    if money_request.status != MoneyRequestStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Request already {money_request.status.value}",
        )

    money_request.status = MoneyRequestStatus.declined
    db.commit()
    db.refresh(money_request)

    return MoneyRequestResponse(
        id=money_request.id,
        requester_id=money_request.requester_id,
        target_id=money_request.target_id,
        amount=money_request.amount,
        status=money_request.status.value,
        created_at=money_request.created_at,
    )


@router.get("", response_model=list[MoneyRequestResponse])
def list_money_requests(
    user_id: UUID = Query(..., description="Filter by user (as requester or target)"),
    status: str | None = Query(
        "pending",
        description="Filter by status: 'pending', 'approved', 'declined', or null/empty for all",
    ),
    db: Session = Depends(get_db),
):
    """
    List money requests where the user is either the requester or the
    target.  Filterable by status (defaults to ``pending``).
    """
    query = (
        db.query(MoneyRequest)
        .filter(
            (MoneyRequest.requester_id == user_id) | (MoneyRequest.target_id == user_id),
        )
    )

    # Apply status filter (default: pending)
    if status and status in ("pending", "approved", "declined"):
        query = query.filter(MoneyRequest.status == MoneyRequestStatus(status))

    requests = (
        query
        .order_by(MoneyRequest.created_at.desc())
        .all()
    )

    return [
        MoneyRequestResponse(
            id=r.id,
            requester_id=r.requester_id,
            target_id=r.target_id,
            amount=r.amount,
            status=r.status.value,
            created_at=r.created_at,
        )
        for r in requests
    ]

