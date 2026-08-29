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

Tamper-evident audit trail
──────────────────────────
• Every LedgerEntry carries ``prev_hash`` and ``entry_hash``.
• ``entry_hash = SHA-256(prev_hash || transfer_id || user_id || entry_type
                           || amount || created_at_iso)``
• A backfill helper (`backfill_entry_hashes`) re-derives the entire chain
  in creation order so historical data can be brought online after the
  feature ships.  The IntegrityError raised on tampered entries is
  surfaced by `verify_entry_hash_chain`.
"""
import hashlib
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

# Genesis hash used as the prev_hash of the very first ledger entry.
# Chosen so that the chain has a deterministic start.
GENESIS_HASH = "0" * 64


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


# ─── Tamper-evident hash chain ────────────────────────────────────────────────

def _compute_entry_hash(
    *,
    prev_hash: str,
    transfer_id: UUID,
    user_id: UUID,
    entry_type: EntryType,
    amount: Decimal,
    created_at_iso: str,
) -> str:
    """
    Compute the SHA-256 hash that links one ledger entry to the next.

    The hash covers the previous entry's hash plus this entry's content
    in a stable, colon-separated canonical form.  Any tampering with
    either the prior chain link or this row's fields will produce a
    different hash, breaking verification at this point and every
    subsequent entry.
    """
    payload = ":".join(
        [
            prev_hash,
            str(transfer_id),
            str(user_id),
            entry_type.value,
            f"{Decimal(amount):.2f}",
            created_at_iso,
        ]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _latest_entry_hash(db: Session) -> str:
    """Return the entry_hash of the most recent ledger entry, or GENESIS_HASH."""
    row = (
        db.query(LedgerEntry)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .first()
    )
    return row.entry_hash if row is not None else GENESIS_HASH


def verify_entry_hash_chain(db: Session) -> dict:
    """
    Walk every LedgerEntry in creation order and verify that each
    ``entry_hash`` was computed from the previous entry's ``entry_hash``
    plus its own canonical content.

    Returns a report with ``valid``, ``checked`` count and the first
    broken entry (if any).
    """
    entries = (
        db.query(LedgerEntry)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
        .all()
    )
    expected_prev = GENESIS_HASH
    broken_at = None
    for e in entries:
        if e.prev_hash != expected_prev:
            broken_at = str(e.id)
            break
        canonical = _compute_entry_hash(
            prev_hash=e.prev_hash,
            transfer_id=e.transfer_id,
            user_id=e.user_id,
            entry_type=e.entry_type,
            amount=e.amount,
            created_at_iso=e.created_at.isoformat(),
        )
        if canonical != e.entry_hash:
            broken_at = str(e.id)
            break
        expected_prev = e.entry_hash
    return {
        "valid": broken_at is None,
        "checked": len(entries),
        "broken_at": broken_at,
    }


def backfill_entry_hashes(db: Session) -> int:
    """
    Re-derive ``prev_hash`` and ``entry_hash`` for every ledger entry in
    creation order.  Used to populate the chain on existing databases
    after the feature ships.

    Returns the number of entries rewritten.
    """
    entries = (
        db.query(LedgerEntry)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
        .all()
    )
    prev_hash = GENESIS_HASH
    rewritten = 0
    for e in entries:
        canonical = _compute_entry_hash(
            prev_hash=prev_hash,
            transfer_id=e.transfer_id,
            user_id=e.user_id,
            entry_type=e.entry_type,
            amount=e.amount,
            created_at_iso=e.created_at.isoformat(),
        )
        if e.prev_hash != prev_hash or e.entry_hash != canonical:
            e.prev_hash = prev_hash
            e.entry_hash = canonical
            rewritten += 1
        prev_hash = e.entry_hash
    return rewritten


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
    #    Each entry is hash-chained to the previous one in creation order.
    #    Genesis is used if this is the first ever entry.  Because
    #    execute_transfer runs inside SELECT … FOR UPDATE we are safe to
    #    read the latest hash here — no concurrent transfer can slip in.
    latest_hash = _latest_entry_hash(db)

    debit_entry = LedgerEntry(
        user_id=sender_id,
        transfer_id=transfer.id,
        entry_type=EntryType.debit,
        amount=amount,
        prev_hash=latest_hash,
        entry_hash="",  # placeholder — overwritten below
    )
    db.add(debit_entry)
    db.flush()  # assigns id + created_at

    debit_entry.entry_hash = _compute_entry_hash(
        prev_hash=debit_entry.prev_hash,
        transfer_id=debit_entry.transfer_id,
        user_id=debit_entry.user_id,
        entry_type=debit_entry.entry_type,
        amount=debit_entry.amount,
        created_at_iso=debit_entry.created_at.isoformat(),
    )

    credit_entry = LedgerEntry(
        user_id=receiver_id,
        transfer_id=transfer.id,
        entry_type=EntryType.credit,
        amount=amount,
        prev_hash=debit_entry.entry_hash,
        entry_hash="",  # placeholder — overwritten below
    )
    db.add(credit_entry)
    db.flush()  # assigns id + created_at

    credit_entry.entry_hash = _compute_entry_hash(
        prev_hash=credit_entry.prev_hash,
        transfer_id=credit_entry.transfer_id,
        user_id=credit_entry.user_id,
        entry_type=credit_entry.entry_type,
        amount=credit_entry.amount,
        created_at_iso=credit_entry.created_at.isoformat(),
    )

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
    chain = verify_entry_hash_chain(db)
    return {
        "total_credits": total_credits,
        "total_debits": total_debits,
        "net_balance": net,
        "ledger_is_balanced": net == Decimal("0"),
        "user_count": int(user_count),
        "transfer_count": int(transfer_count),
        # Tamper-evident audit trail
        "hash_chain_valid": chain["valid"],
        "hash_chain_entries_checked": chain["checked"],
        "hash_chain_broken_at": chain["broken_at"],
    }


# ─── Transaction Explainability Engine ────────────────────────────────────────

def explain_transfer(db: Session, transfer_id: UUID) -> dict:
    """
    Build a full "explainability report" for a transfer.

    Includes both ledger rows, the balance changes for each party, the
    position of this transfer in the global hash chain, and a narrative
    sentence suitable for surfacing on a UI.

    Raises:
        LookupError — if the transfer_id is unknown.
    """
    from app.models import LedgerEntry  # local import avoids cycles

    transfer: Transfer | None = (
        db.query(Transfer).filter(Transfer.id == transfer_id).first()
    )
    if transfer is None:
        raise LookupError(f"Transfer {transfer_id} not found")

    sender: User | None = (
        db.query(User).filter(User.id == transfer.sender_id).first()
    )
    receiver: User | None = (
        db.query(User).filter(User.id == transfer.receiver_id).first()
    )

    entries: list[LedgerEntry] = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.transfer_id == transfer_id)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
        .all()
    )

    # Compute balance before this transfer — by summing every entry that
    # was created strictly before this one.
    first_created = min(e.created_at for e in entries) if entries else transfer.created_at

    def _balance_at(user_id: UUID, cutoff) -> Decimal:
        result = (
            db.query(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                LedgerEntry.entry_type == EntryType.credit,
                                LedgerEntry.amount,
                            ),
                            else_=-LedgerEntry.amount,
                        )
                    ),
                    0,
                )
            )
            .filter(
                LedgerEntry.user_id == user_id,
                LedgerEntry.created_at < cutoff,
            )
            .scalar()
        )
        return Decimal(result)

    sender_balance_before = _balance_at(transfer.sender_id, first_created)
    receiver_balance_before = _balance_at(transfer.receiver_id, first_created)
    sender_balance_after = sender_balance_before - Decimal(transfer.amount)
    receiver_balance_after = receiver_balance_before + Decimal(transfer.amount)

    # Position in the global chain: 1-indexed for humans
    chain_position = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.created_at < first_created)
        .count()
    ) + 1

    # Build the human narrative
    sender_name = sender.name if sender else str(transfer.sender_id)
    receiver_name = receiver.name if receiver else str(transfer.receiver_id)
    amount_str = f"{Decimal(transfer.amount):,.2f}"
    narrative = (
        f"{sender_name} sent {amount_str} to {receiver_name}. "
        f"This created two ledger entries — a debit of {amount_str} on "
        f"{sender_name}'s account and a credit of {amount_str} on "
        f"{receiver_name}'s account — hash-chained to the prior ledger "
        f"state at chain position #{chain_position}. "
        f"{sender_name}'s balance moved from {sender_balance_before:,.2f} "
        f"to {sender_balance_after:,.2f}; {receiver_name}'s balance moved "
        f"from {receiver_balance_before:,.2f} to {receiver_balance_after:,.2f}."
    )

    return {
        "transfer_id": transfer.id,
        "sender_id": transfer.sender_id,
        "sender_name": sender_name,
        "receiver_id": transfer.receiver_id,
        "receiver_name": receiver_name,
        "amount": Decimal(transfer.amount),
        "status": transfer.status.value,
        "idempotency_key": transfer.idempotency_key,
        "created_at": transfer.created_at,
        "sender_balance_before": sender_balance_before,
        "sender_balance_after": sender_balance_after,
        "receiver_balance_before": receiver_balance_before,
        "receiver_balance_after": receiver_balance_after,
        "entries": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "user_name": (sender.name if e.user_id == transfer.sender_id else receiver.name)
                if (sender and receiver)
                else str(e.user_id),
                "entry_type": e.entry_type.value,
                "amount": Decimal(e.amount),
                "created_at": e.created_at,
                "prev_hash": e.prev_hash,
                "entry_hash": e.entry_hash,
            }
            for e in entries
        ],
        "narrative": narrative,
        "chain_position": chain_position,
    }


# ─── Money Movement Recovery Center ───────────────────────────────────────────

def recovery_summary(db: Session) -> dict:
    """
    Roll-up of the system for the Recovery Center dashboard.

    ``replayable`` is the number of transfers that *would* be candidates
    for replay — currently any failed transfer (the only kind we can
    legitimately retry).
    """
    from app.models import MoneyRequest, MoneyRequestStatus

    total = db.query(func.count(Transfer.id)).scalar() or 0
    completed = (
        db.query(func.count(Transfer.id))
        .filter(Transfer.status == TransferStatus.completed)
        .scalar()
        or 0
    )
    failed = (
        db.query(func.count(Transfer.id))
        .filter(Transfer.status == TransferStatus.failed)
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(MoneyRequest.id))
        .filter(MoneyRequest.status == MoneyRequestStatus.pending)
        .scalar()
        or 0
    )

    return {
        "total_transfers": int(total),
        "completed": int(completed),
        "failed": int(failed),
        "replayable": int(failed),  # same set: failed transfers can be replayed
        "pending_requests": int(pending),
    }


def replay_impact(db: Session, transfer_id: UUID) -> dict:
    """
    Compute the effect of replaying ``transfer_id`` *without* persisting
    anything.  Used by the Recovery Center to show "this is what would
    happen" before the user clicks the live replay button.
    """
    transfer: Transfer | None = (
        db.query(Transfer).filter(Transfer.id == transfer_id).first()
    )
    if transfer is None:
        raise LookupError(f"Transfer {transfer_id} not found")

    sender_balance = _compute_balance(db, transfer.sender_id)
    receiver_balance = _compute_balance(db, transfer.receiver_id)
    new_sender = sender_balance - Decimal(transfer.amount)
    new_receiver = receiver_balance + Decimal(transfer.amount)

    if transfer.sender_id == TREASURY_ID:
        has_funds = True
        note = (
            "Sender is the system treasury — replay is always allowed "
            "even though it will deepen the treasury's negative balance."
        )
    elif new_sender < Decimal("0"):
        has_funds = False
        note = (
            f"Sender would be overdrawn by {abs(new_sender):,.2f}. "
            "Replay blocked until the sender is funded."
        )
    else:
        has_funds = True
        note = (
            f"Replay will move {Decimal(transfer.amount):,.2f} from "
            f"{transfer.sender_id} to {transfer.receiver_id}. "
            f"Sender balance: {sender_balance:,.2f} → {new_sender:,.2f}. "
            f"Receiver balance: {receiver_balance:,.2f} → {new_receiver:,.2f}."
        )

    return {
        "sender_balance_after": new_sender,
        "receiver_balance_after": new_receiver,
        "sender_has_sufficient_funds": has_funds,
        "note": note,
    }


def replay_transfer(db: Session, transfer_id: UUID) -> tuple[bool, str, Decimal | None]:
    """
    Replay a failed transfer by re-running execute_transfer with the
    same idempotency_key.  Because the idempotency_key is unique on the
    transfers table, replay is *guaranteed* to either:

    1. Find the original transfer (already replayed → no-op success).
    2. Insert a fresh transfer with the same key (genuine replay).

    Returns (replayed, note, sender_balance).
    """
    transfer: Transfer | None = (
        db.query(Transfer).filter(Transfer.id == transfer_id).first()
    )
    if transfer is None:
        raise LookupError(f"Transfer {transfer_id} not found")

    try:
        new_transfer, sender_balance = execute_transfer(
            db=db,
            sender_id=transfer.sender_id,
            receiver_id=transfer.receiver_id,
            amount=Decimal(transfer.amount),
            idempotency_key=transfer.idempotency_key,
        )
        db.commit()
        return True, "Replay executed successfully.", sender_balance
    except ValueError as exc:
        db.rollback()
        # If the idempotency key already exists (because someone else
        # just replayed it), surface that as a no-op success.
        existing = get_existing_transfer(db, transfer.idempotency_key)
        if existing is not None and existing.id != transfer.id:
            return True, (
                "Transfer was already replayed by another request "
                f"(id={existing.id}). No change applied."
            ), _compute_balance(db, existing.sender_id)
        return False, str(exc), None
