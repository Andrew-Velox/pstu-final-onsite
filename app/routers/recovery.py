"""
Money Movement Recovery Center router.

Endpoints
─────────
GET  /recovery/summary              → roll-up counts (total/completed/failed/pending)
GET  /recovery/replay/{id}/impact   → dry-run impact analysis (no writes)
POST /recovery/replay               → re-execute a failed transfer (idempotent)

Why this exists
───────────────
Real money movement is lossy. Networks blip, processes crash mid-flight,
and clients retry. The Recovery Center is the operator UI for the
"what broke, what do we re-run" questions.  Every replay is idempotent —
re-running it twice will not double-debit the sender — because we reuse
the original ``idempotency_key`` of the transfer.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    ReplayImpact,
    ReplayRequest,
    ReplayResponse,
    RecoverySummary,
)
from app.services import (
    recovery_summary,
    replay_impact,
    replay_transfer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recovery", tags=["recovery"])


@router.get("/summary", response_model=RecoverySummary)
def get_recovery_summary(db: Session = Depends(get_db)) -> RecoverySummary:
    """
    Headline numbers for the Recovery Center dashboard.

    • ``total_transfers``    – every Transfer row in the system.
    • ``completed``          – status == completed.
    • ``failed``             – status == failed.
    • ``replayable``         – currently equal to ``failed`` (the only
                              transfers that can be safely replayed).
    • ``pending_requests``   – outstanding MoneyRequest rows waiting
                              for a target to approve or decline.
    """
    return RecoverySummary(**recovery_summary(db))


@router.get(
    "/replay/{transfer_id}/impact",
    response_model=ReplayImpact,
)
def get_replay_impact(
    transfer_id: UUID,
    db: Session = Depends(get_db),
) -> ReplayImpact:
    """
    Compute the effect of replaying ``transfer_id`` *without* persisting
    any changes.  The Recovery Center UI shows this before letting the
    operator click the live replay button.
    """
    try:
        return ReplayImpact(**replay_impact(db, transfer_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/replay", response_model=ReplayResponse)
def post_replay(
    body: ReplayRequest,
    db: Session = Depends(get_db),
) -> ReplayResponse:
    """
    Replay a transfer by id.  Safe to call twice — the underlying
    ``execute_transfer`` is idempotent on the original
    ``idempotency_key``.

    Returns a structured response so the UI can show "succeeded" or
    surface the reason a replay would overdraft the sender.
    """
    try:
        replayed, note, sender_balance = replay_transfer(db, body.transfer_id)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return ReplayResponse(
        replayed=replayed,
        transfer_id=body.transfer_id,
        note=note,
        sender_balance=sender_balance,
    )
