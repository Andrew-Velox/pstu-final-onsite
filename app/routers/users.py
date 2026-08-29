"""
User-facing read endpoints — transaction history and balance.

Endpoints
─────────
GET /users/{user_id}/transactions — paginated ledger activity
GET /users/{user_id}/balance      — current computed balance
"""

import enum
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.models import EntryType, LedgerEntry, Transfer, User
from app.schemas import (
    BalanceResponse,
    TransactionItem,
    TransactionListResponse,
    UserCreate,
    UserResponse,
)
from app.services import (
    register_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(db: Session = Depends(get_db)):
    """Return all users (for the frontend user-switcher)."""
    users = db.query(User).order_by(User.name).all()
    return [
        {"id": str(u.id), "name": u.name, "email": u.email}
        for u in users
    ]


# ─── POST /users — registration with auto-funding ────────────────────────────

@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
):
    """
    Register a new user and credit them with the starting balance from
    the system treasury.

    All of the following happen in a single DB transaction:
      1. Insert the new ``users`` row.
      2. Insert a ``transfers`` row (sender=treasury, receiver=new user).
      3. Insert the matching pair of ``ledger_entries`` (debit treasury,
         credit new user) via the same ``execute_transfer`` path used by
         every other transfer.

    The funding transfer's idempotency key is ``seed-{user_id}``, so a
    retried registration can never double-fund the user.
    """
    try:
        new_user, starting_balance = register_user(
            db=db,
            name=body.name,
            email=body.email,
        )
        db.commit()
        db.refresh(new_user)

        return UserResponse(
            id=new_user.id,
            name=new_user.name,
            email=new_user.email,
            balance=starting_balance,
            created_at=new_user.created_at,
        )

    except ValueError as exc:
        db.rollback()
        logger.warning("Registration rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:
        db.rollback()
        logger.exception("Unexpected error during user registration")
        raise HTTPException(status_code=500, detail="Internal server error")


class TypeFilter(str, enum.Enum):
    """Query parameter for filtering transaction direction."""
    all = "all"
    sent = "sent"
    received = "received"


# ─── GET /users/{user_id}/transactions ────────────────────────────────────────

@router.get(
    "/{user_id}/transactions",
    response_model=TransactionListResponse,
)
def get_transactions(
    user_id: UUID,
    limit: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    type: TypeFilter = Query(
        TypeFilter.all,
        description="Filter: 'sent' (debits), 'received' (credits), or 'all'",
    ),
    db: Session = Depends(get_db),
):
    """
    Return a paginated list of this user's ledger activity, most recent
    first.  Each row is joined with the Transfer to resolve the
    counterparty (the other user in the transfer).

    The response is shaped for direct frontend rendering — flat objects
    with direction, counterparty name, and timestamp.
    """
    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # ── Build base query ──────────────────────────────────────────────────
    # Alias for the counterparty user (the OTHER side of each transfer).
    Counterparty = aliased(User)

    # For a DEBIT entry: this user is the sender, counterparty is receiver.
    # For a CREDIT entry: this user is the receiver, counterparty is sender.
    counterparty_id_expr = case(
        (LedgerEntry.entry_type == EntryType.debit, Transfer.receiver_id),
        else_=Transfer.sender_id,
    )

    query = (
        db.query(
            LedgerEntry.transfer_id,
            LedgerEntry.entry_type,
            LedgerEntry.amount,
            LedgerEntry.created_at,
            counterparty_id_expr.label("counterparty_id"),
            Counterparty.name.label("counterparty_name"),
        )
        .join(Transfer, LedgerEntry.transfer_id == Transfer.id)
        .join(
            Counterparty,
            Counterparty.id == counterparty_id_expr,
        )
        .filter(LedgerEntry.user_id == user_id)
    )

    # ── Apply type filter ─────────────────────────────────────────────────
    if type == TypeFilter.sent:
        query = query.filter(LedgerEntry.entry_type == EntryType.debit)
    elif type == TypeFilter.received:
        query = query.filter(LedgerEntry.entry_type == EntryType.credit)

    # ── Count total (before pagination) ───────────────────────────────────
    total = query.count()

    # ── Paginate ──────────────────────────────────────────────────────────
    rows = (
        query
        .order_by(LedgerEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        TransactionItem(
            transfer_id=row.transfer_id,
            direction="sent" if row.entry_type == EntryType.debit else "received",
            amount=row.amount,
            counterparty_id=row.counterparty_id,
            counterparty_name=row.counterparty_name,
            timestamp=row.created_at,
        )
        for row in rows
    ]

    return TransactionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /users/{user_id}/balance ─────────────────────────────────────────────

@router.get("/{user_id}/balance", response_model=BalanceResponse)
def get_balance(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Return the user's current computed balance.

    balance = SUM(credit amounts) - SUM(debit amounts)
    """
    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    balance = db.query(
        func.coalesce(
            func.sum(
                case(
                    (LedgerEntry.entry_type == EntryType.credit, LedgerEntry.amount),
                    else_=-LedgerEntry.amount,
                )
            ),
            0,
        )
    ).filter(
        LedgerEntry.user_id == user_id,
    ).scalar()

    return BalanceResponse(
        user_id=user_id,
        balance=balance,
    )
