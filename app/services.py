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

Treasury account
────────────────
• ``TREASURY_ID`` is a fixed UUID that identifies the system account which
  funds every newly registered user with a 100000 starting balance.
• The treasury is allowed to have a negative balance — it is the source
  of new money in the system.  Therefore the ``insufficient funds`` check
  in ``execute_transfer`` is bypassed when the sender is the treasury.
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


# ─── Treasury (system funding account) ───────────────────────────────────────

# Fixed UUID for the system treasury.  Hard-coded so that every process in
# every environment agrees on its identity without needing a migration step
# to discover it.  Changing this constant would orphan every existing
# user's funding transfer — do not change it.
TREASURY_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")
TREASURY_EMAIL = "treasury@system.internal"
TREASURY_NAME = "System Treasury"
STARTING_BALANCE = Decimal("100000")


def seed_treasury(db: Session) -> User:
    """
    Ensure the treasury User row exists.  Safe to call on every startup —
    it's a no-op once the row is present.

    Does NOT commit — the caller owns the transaction.  This makes it
    safe to call from inside ``register_user`` (which needs to roll the
    whole thing back together if anything fails) as well as from the
    FastAPI startup hook (which commits the dedicated seed session).

    The treasury is intentionally given **no** opening balance.  It starts
    at zero and goes negative as it funds new users, which is fine: the
    ``execute_transfer`` insufficient-funds check is bypassed for
    treasury-originated transfers.
    """
    existing = (
        db.query(User)
        .filter(User.id == TREASURY_ID)
        .first()
    )
    if existing is not None:
        return existing

    treasury = User(
        id=TREASURY_ID,
        name=TREASURY_NAME,
        email=TREASURY_EMAIL,
    )
    db.add(treasury)
    db.flush()  # makes treasury.id usable without committing
    return treasury


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

    # The treasury is the source of all new money in the system, so its
    # balance is allowed to go negative.  Only normal users get the
    # insufficient-funds guard.
    if sender_id != TREASURY_ID and sender_balance < amount:
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


# ─── User registration (auto-funded from treasury) ───────────────────────────

def register_user(
    db: Session,
    name: str,
    email: str,
) -> tuple[User, Decimal]:
    """
    Register a new user and credit them ``STARTING_BALANCE`` from the
    treasury, all inside a single DB transaction.

    The funding step reuses ``execute_transfer`` (the same code path as
    any other transfer) so the same double-entry invariants hold: one
    Transfer row, two LedgerEntry rows (debit treasury, credit new user).

    Idempotency: ``seed-{new_user.id}`` is a deterministic idempotency
    key, so a retry of the same registration cannot double-fund the user.

    Returns ``(User, starting_balance)``.

    Raises:
        ValueError  – if a user with this email already exists.
    """
    # ── 1. Reject duplicate emails up front ──────────────────────────────
    existing = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )
    if existing is not None:
        raise ValueError(f"A user with email {email!r} already exists")

    # ── 2. Ensure the treasury exists (no-op after first startup) ────────
    seed_treasury(db)

    # ── 3. Create the new user row ──────────────────────────────────────
    new_user = User(name=name, email=email)
    db.add(new_user)
    db.flush()  # assigns new_user.id

    # ── 4. Fund them via the standard double-entry transfer path ────────
    execute_transfer(
        db=db,
        sender_id=TREASURY_ID,
        receiver_id=new_user.id,
        amount=STARTING_BALANCE,
        idempotency_key=f"seed-{new_user.id}",
    )

    return new_user, STARTING_BALANCE


def system_ledger_health(db: Session) -> dict:
    """
    Sum every ledger entry in the system and prove that credits equal
    debits (the net must be zero).

    Returns a dict with totals and a boolean for live demonstrations.
    """
    row = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.entry_type == EntryType.credit, LedgerEntry.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("total_credits"),
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.entry_type == EntryType.debit, LedgerEntry.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("total_debits"),
        )
        .one()
    )

    user_count = db.query(func.count(User.id)).scalar() or 0
    transfer_count = db.query(func.count(Transfer.id)).scalar() or 0

    total_credits = Decimal(row.total_credits)
    total_debits = Decimal(row.total_debits)
    net = total_credits - total_debits
    return {
        "total_credits": total_credits,
        "total_debits": total_debits,
        "net_balance": net,
        "ledger_is_balanced": net == Decimal("0"),
        "user_count": int(user_count),
        "transfer_count": int(transfer_count),
    }
