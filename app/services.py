"""
Transfer service — core double-entry ledger logic.

Concurrency safety
──────────────────
• Both the sender and receiver rows are locked with SELECT … FOR UPDATE
  inside a single transaction.
• To prevent AB/BA deadlocks, rows are always locked in ascending UUID
  order regardless of who is the sender and who is the receiver.
• The sender's balance is computed *inside* the locked transaction, so
  two concurrent transfers from the same sender are serialised correctly.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import (
    EntryType,
    LedgerEntry,
    Transfer,
    TransferStatus,
    User,
)


def _compute_balance(db: Session, user_id: UUID) -> Decimal:
    """
    Derive a user's current balance from ledger entries.

    balance = SUM(credit amounts) − SUM(debit amounts)

    Must be called inside a transaction that already holds a FOR UPDATE
    lock on the user row to be safe under concurrency.
    """
    result = db.query(
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

    return Decimal(result)


def get_existing_transfer(db: Session, idempotency_key: str) -> Transfer | None:
    """Return an existing Transfer with this idempotency_key, or None."""
    return (
        db.query(Transfer)
        .filter(Transfer.idempotency_key == idempotency_key)
        .first()
    )


def execute_transfer(
    db: Session,
    sender_id: UUID,
    receiver_id: UUID,
    amount: Decimal,
    idempotency_key: str,
) -> tuple[Transfer, Decimal]:
    """
    Execute a peer-to-peer money transfer inside a single DB transaction.

    Returns (Transfer, sender_new_balance).

    Raises:
        ValueError  – if sender == receiver, users not found, or
                      insufficient funds.
    """
    if sender_id == receiver_id:
        raise ValueError("Sender and receiver must be different users")

    # ── 1. Lock both user rows in consistent UUID order ───────────────────
    #    Sorting prevents AB/BA deadlocks when two transfers between the
    #    same pair of users run concurrently in opposite directions.
    ordered_ids = sorted([sender_id, receiver_id])

    locked_users = (
        db.query(User)
        .filter(User.id.in_(ordered_ids))
        .order_by(User.id)
        .with_for_update()
        .all()
    )

    if len(locked_users) != 2:
        raise ValueError("One or both users not found")

    # ── 2. Compute sender balance inside the lock ─────────────────────────
    sender_balance = _compute_balance(db, sender_id)

    if sender_balance < amount:
        raise ValueError(
            f"Insufficient funds: balance={sender_balance}, required={amount}"
        )

    # ── 3. Create the Transfer row ────────────────────────────────────────
    transfer = Transfer(
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=amount,
        status=TransferStatus.completed,
        idempotency_key=idempotency_key,
    )
    db.add(transfer)
    db.flush()  # assigns transfer.id for the FK below

    # ── 4. Create exactly two LedgerEntry rows ───────────────────────────
    debit_entry = LedgerEntry(
        user_id=sender_id,
        transfer_id=transfer.id,
        entry_type=EntryType.debit,
        amount=amount,
    )
    credit_entry = LedgerEntry(
        user_id=receiver_id,
        transfer_id=transfer.id,
        entry_type=EntryType.credit,
        amount=amount,
    )
    db.add_all([debit_entry, credit_entry])

    # ── 5. Compute updated sender balance ─────────────────────────────────
    new_balance = sender_balance - amount

    return transfer, new_balance
