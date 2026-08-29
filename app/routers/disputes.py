"""
Money Movement Protection / Dispute endpoints.

These routes back the in-app "Dispute Center" that lets a sender file
a claim against a transfer they sent in error.  See ``app.services``
for the business logic (3-digit tolerance, 15-day hold, clawback
flow).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    AvailableBalanceResponse,
    DisputeAdminResolveBody,
    DisputeCreate,
    DisputeListResponse,
    DisputeRespondBody,
    DisputeResponse,
    NotificationListResponse,
)
from app.services import (
    admin_resolve,
    auto_refund_expired,
    compute_available_balance,
    dispute_detail,
    file_dispute,
    list_disputes,
    list_notifications,
    mark_notifications_read,
    receiver_respond,
)


router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.post("", response_model=DisputeResponse, status_code=201)
def file_dispute_endpoint(body: DisputeCreate, db: Session = Depends(get_db)):
    """
    File a new dispute.

    Validation enforced (see ``file_dispute``):
      - complainant must be the original sender
      - transfer must be completed and ≤ 15 days old
      - no active dispute already exists
      - |claimed_amount - requested_amount| ≤ 3
      - screenshot_url must be http(s) or a data: URI
    """
    try:
        d = file_dispute(
            db,
            transfer_id=body.transfer_id,
            complainant_id=body.complainant_id,
            screenshot_url=body.screenshot_url,
            claimed_amount=body.claimed_amount,
            requested_amount=body.requested_amount,
            narrative=body.narrative,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Trigger a sweep first so any just-expired disputes get refunded.
    auto_refund_expired(db)
    return dispute_detail(db, d.id)


@router.get("", response_model=DisputeListResponse)
def list_my_disputes(
    user_id: UUID = Query(..., description="User whose disputes to list"),
    db: Session = Depends(get_db),
):
    """
    List disputes where the user is either complainant or respondent.

    Also includes a global sweep so any expired disputes are
    auto-refunded before the response is computed.
    """
    auto_refund_expired(db)
    return list_disputes(db, user_id)


@router.get("/notifications", response_model=NotificationListResponse)
def my_notifications(
    user_id: UUID = Query(..., description="User whose notifications to fetch"),
    db: Session = Depends(get_db),
):
    return list_notifications(db, user_id)


@router.post("/notifications/read-all")
def mark_all_read(
    user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    n = mark_notifications_read(db, user_id)
    return {"marked_read": n}


@router.get("/{dispute_id}", response_model=DisputeResponse)
def get_dispute_endpoint(dispute_id: UUID, db: Session = Depends(get_db)):
    auto_refund_expired(db)
    try:
        return dispute_detail(db, dispute_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{dispute_id}/respond", response_model=DisputeResponse)
def receiver_respond_endpoint(
    dispute_id: UUID,
    body: DisputeRespondBody,
    db: Session = Depends(get_db),
):
    """
    The respondent (receiver of the disputed transfer) submits their
    response.  If ``accept_refund=true`` the system immediately runs the
    clawback and marks the dispute resolved.
    """
    try:
        receiver_respond(
            db,
            dispute_id=dispute_id,
            user_id=body.user_id,
            response_text=body.response,
            accept_refund=body.accept_refund,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return dispute_detail(db, dispute_id)


@router.post("/{dispute_id}/admin-resolve", response_model=DisputeResponse)
def admin_resolve_endpoint(
    dispute_id: UUID,
    body: DisputeAdminResolveBody,
    db: Session = Depends(get_db),
):
    """Admin force-resolves a dispute."""
    try:
        admin_resolve(
            db,
            dispute_id=dispute_id,
            admin_id=body.admin_id,
            resolution=body.resolution,
            note=body.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return dispute_detail(db, dispute_id)


@router.post("/sweep-expired")
def sweep_expired_endpoint(db: Session = Depends(get_db)):
    """
    Manually trigger the auto-refund sweep.  Normally called from the
    list/notification endpoints but exposed here for cron-style usage.
    """
    n = auto_refund_expired(db)
    return {"auto_refunded": n}


# Available-balance lives under /users but is implemented here to keep
# the dispute-aware logic colocated with the rest of the dispute code.
from fastapi import APIRouter as _APIRouter  # noqa: E402  (kept for clarity)
user_router = _APIRouter(prefix="/users", tags=["users"])


@user_router.get("/{user_id}/available-balance", response_model=AvailableBalanceResponse)
def available_balance_endpoint(user_id: UUID, db: Session = Depends(get_db)):
    """
    GET /users/{user_id}/available-balance

    Returns the user's ledger balance, the amount currently held by
    active disputes, and the resulting spendable balance.
    """
    res = compute_available_balance(db, user_id)
    return {
        "user_id": user_id,
        "balance": res["balance"],
        "held": res["held"],
        "available": res["available"],
    }