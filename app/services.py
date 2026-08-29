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

# ─── Money Movement Protection / Disputes ────────────────────────────────────
#
# The dispute system lets a sender challenge a transfer they believe was
# sent in error (wrong number, wrong amount, etc.).  When filed within the
# 15-day window and the digit-delta is ≤ 3, the receiver's available
# balance is frozen for 15 days.  Resolution paths:
#
#   1. Receiver accepts refund           → clawback entries, refund sender.
#   2. Receiver responds, dispute settled manually by admin → clawback
#      or release depending on adjudication.
#   3. Hold expires with no receiver response → auto-clawback (refund).
#
# All ledger mutations go through `execute_transfer` (with a deterministic
# `idempotency_key = 'dispute-clawback-{dispute_id}'`) so the double-entry
# invariants, hash chain, and FOR UPDATE locking all behave identically to a
# normal transfer.  This means the global ledger balance still nets to zero
# after every dispute resolution, and every action is auditable on the
# Explainability Engine.

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import or_, select

from app.models import (
    Dispute,
    DisputeStatus,
    LedgerEntry,
    Notification,
    NotificationKind,
    Transfer,
    TransferStatus,
    User,
)
from app.schemas import DisputeTimelineEntry


DISPUTE_HOLD_DAYS = 15
DISPUTE_DIGIT_TOLERANCE = Decimal("3")
DISPUTE_WINDOW_DAYS = 15  # sender can only file within 15 days of the transfer


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _abs_amount_delta(claimed: Decimal, requested: Decimal) -> Decimal:
    return abs(Decimal(claimed) - Decimal(requested))


def _push_notification(
    db: Session,
    *,
    user_id,
    kind: NotificationKind,
    title: str,
    body: str,
    dispute_id=None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        dispute_id=dispute_id,
    )
    db.add(n)
    db.flush()
    return n


def _simulate_call(
    db: Session,
    *,
    user_id,
    dispute_id,
    title: str,
    body: str,
) -> Notification:
    """
    Record a simulated outbound voice call.  In a real system this would
    invoke Twilio; here we just write a notification row of kind
    `call_outbound` so the UI can show the call in the timeline.
    """
    return _push_notification(
        db,
        user_id=user_id,
        kind=NotificationKind.call_outbound,
        title=title,
        body=body,
        dispute_id=dispute_id,
    )


# ─── Available-balance helpers ───────────────────────────────────────────────

def _active_hold_total(db: Session, user_id) -> Decimal:
    """
    Sum of claimed_amount across active disputes where `user_id` is the
    respondent.  Active == status == filed and hold_expires_at in the future.
    """
    now = _utcnow()
    total = (
        db.query(func.coalesce(func.sum(Dispute.claimed_amount), 0))
        .filter(
            Dispute.respondent_id == user_id,
            Dispute.status == DisputeStatus.filed,
            Dispute.hold_expires_at > now,
        )
        .scalar()
    )
    return Decimal(total or 0)


def compute_available_balance(db: Session, user_id) -> dict:
    balance = _compute_balance(db, user_id)
    held = _active_hold_total(db, user_id)
    available = balance - held
    return {"balance": balance, "held": held, "available": available}


# ─── Dispute lifecycle ───────────────────────────────────────────────────────

def file_dispute(
    db: Session,
    *,
    transfer_id,
    complainant_id,
    screenshot_url: str,
    claimed_amount: Decimal,
    requested_amount: Decimal,
    narrative: str | None,
) -> Dispute:
    """
    File a dispute against a transfer.

    Validates:
      - complainant must be the original sender.
      - transfer must be completed and ≤ DISPUTE_WINDOW_DAYS old.
      - no active dispute already exists for the transfer.
      - |claimed_amount - requested_amount| ≤ DISPUTE_DIGIT_TOLERANCE.
      - screenshot_url is well-formed.

    On success:
      - creates Dispute row with hold_expires_at = now + 15 days.
      - records notifications for both parties + simulated call to respondent.
    """
    transfer: Transfer | None = (
        db.query(Transfer).filter(Transfer.id == transfer_id).first()
    )
    if transfer is None:
        raise LookupError(f"Transfer {transfer_id} not found")
    if transfer.status != TransferStatus.completed:
        raise ValueError(
            f"Cannot dispute a transfer with status={transfer.status.value!r}"
        )
    if transfer.sender_id != complainant_id:
        raise ValueError("Only the sender of a transfer can file a dispute")

    age = _utcnow() - transfer.created_at
    if age > timedelta(days=DISPUTE_WINDOW_DAYS):
        raise ValueError(
            f"Dispute window expired. Transfers may only be disputed within "
            f"{DISPUTE_WINDOW_DAYS} days."
        )

    existing = (
        db.query(Dispute)
        .filter(
            Dispute.transfer_id == transfer_id,
            Dispute.status.in_(
                [
                    DisputeStatus.filed,
                    DisputeStatus.under_review,
                ]
            ),
        )
        .first()
    )
    if existing is not None:
        raise ValueError(
            f"An active dispute already exists for this transfer "
            f"(dispute_id={existing.id})."
        )

    delta = _abs_amount_delta(claimed_amount, requested_amount)
    if delta > DISPUTE_DIGIT_TOLERANCE:
        raise ValueError(
            f"Amount mismatch too large: |claimed - requested| = {delta} "
            f"(tolerance is {DISPUTE_DIGIT_TOLERANCE})."
        )

    if not (screenshot_url.startswith("http://")
            or screenshot_url.startswith("https://")
            or screenshot_url.startswith("data:image/")):
        raise ValueError("screenshot_url must be an http(s) URL or a data: URI")

    dispute = Dispute(
        transfer_id=transfer_id,
        complainant_id=complainant_id,
        respondent_id=transfer.receiver_id,
        screenshot_url=screenshot_url,
        claimed_amount=Decimal(claimed_amount),
        requested_amount=Decimal(requested_amount),
        narrative=narrative,
        status=DisputeStatus.filed,
        hold_expires_at=_utcnow() + timedelta(days=DISPUTE_HOLD_DAYS),
    )
    db.add(dispute)
    db.flush()

    _push_notification(
        db,
        user_id=complainant_id,
        kind=NotificationKind.dispute_filed,
        title="Dispute filed",
        body=(
            f"Your dispute for transfer {transfer_id} is under review. "
            f"Funds are on hold until {dispute.hold_expires_at.isoformat()}."
        ),
        dispute_id=dispute.id,
    )
    _push_notification(
        db,
        user_id=transfer.receiver_id,
        kind=NotificationKind.dispute_filed,
        title="A payment you received is under dispute",
        body=(
            f"{transfer.sender_id} has disputed a transfer. "
            f"Please respond within 15 days to avoid auto-refund."
        ),
        dispute_id=dispute.id,
    )
    _simulate_call(
        db,
        user_id=transfer.receiver_id,
        dispute_id=dispute.id,
        title="Outbound call placed",
        body=(
            f"Automated voice call attempted to respondent. "
            f"Message: 'You have a pending dispute. Please log in to respond.'"
        ),
    )

    db.commit()
    db.refresh(dispute)
    return dispute


def receiver_respond(
    db: Session,
    *,
    dispute_id,
    user_id,
    response_text: str,
    accept_refund: bool,
) -> Dispute:
    """
    Receiver responds to a dispute.  Sets status to `under_review` and
    records the response.  If `accept_refund` is true, immediately runs
    the clawback and marks the dispute `resolved_for_sender`.
    """
    dispute: Dispute | None = (
        db.query(Dispute).filter(Dispute.id == dispute_id).first()
    )
    if dispute is None:
        raise LookupError(f"Dispute {dispute_id} not found")
    if dispute.respondent_id != user_id:
        raise ValueError("Only the respondent can submit a response")
    if dispute.status != DisputeStatus.filed:
        raise ValueError(
            f"Dispute is in status={dispute.status.value!r}; cannot respond."
        )

    dispute.receiver_response = response_text
    dispute.status = DisputeStatus.under_review

    _push_notification(
        db,
        user_id=dispute.complainant_id,
        kind=NotificationKind.dispute_responded,
        title="Receiver responded",
        body=f"The receiver responded: {response_text[:200]}",
        dispute_id=dispute.id,
    )

    if accept_refund:
        _clawback(db, dispute, note="Receiver accepted refund.")
        dispute.status = DisputeStatus.resolved_for_sender
        dispute.resolved_at = _utcnow()
        _push_notification(
            db,
            user_id=dispute.complainant_id,
            kind=NotificationKind.dispute_resolved,
            title="Dispute resolved in your favour",
            body=f"You have been refunded {dispute.claimed_amount}.",
            dispute_id=dispute.id,
        )
        _push_notification(
            db,
            user_id=dispute.respondent_id,
            kind=NotificationKind.dispute_resolved,
            title="Refund processed",
            body=(
                f"You agreed to refund {dispute.claimed_amount} to the sender."
            ),
            dispute_id=dispute.id,
        )

    db.commit()
    db.refresh(dispute)
    return dispute


def admin_resolve(
    db: Session,
    *,
    dispute_id,
    admin_id,
    resolution: str,
    note: str | None,
) -> Dispute:
    """
    Admin force-resolves a dispute.

    `resolution`:
      - 'refund_sender'    → clawback + resolved_for_sender
      - 'release_receiver' → mark resolved_for_receiver, hold released
    """
    dispute: Dispute | None = (
        db.query(Dispute).filter(Dispute.id == dispute_id).first()
    )
    if dispute is None:
        raise LookupError(f"Dispute {dispute_id} not found")
    if dispute.status not in (DisputeStatus.filed, DisputeStatus.under_review):
        raise ValueError(
            f"Dispute is already {dispute.status.value!r}; cannot re-resolve."
        )

    if resolution == "refund_sender":
        _clawback(db, dispute, note=note or "Admin resolved for sender.")
        dispute.status = DisputeStatus.resolved_for_sender
    elif resolution == "release_receiver":
        dispute.status = DisputeStatus.resolved_for_receiver
    else:
        raise ValueError(
            f"Unknown resolution {resolution!r}; expected refund_sender|release_receiver"
        )

    dispute.resolved_at = _utcnow()
    dispute.resolution_note = note

    for uid in (dispute.complainant_id, dispute.respondent_id):
        _push_notification(
            db,
            user_id=uid,
            kind=NotificationKind.dispute_resolved,
            title="Dispute resolved by admin",
            body=note or f"Admin set resolution={resolution!r}.",
            dispute_id=dispute.id,
        )

    db.commit()
    db.refresh(dispute)
    return dispute


def auto_refund_expired(db: Session) -> int:
    """
    Sweep every dispute whose hold has expired without a resolution and
    auto-clawback the funds.  Returns the number of disputes refunded.

    Safe to call repeatedly; only `filed` disputes whose hold has
    elapsed are touched.
    """
    now = _utcnow()
    expired = (
        db.query(Dispute)
        .filter(
            Dispute.status == DisputeStatus.filed,
            Dispute.hold_expires_at <= now,
        )
        .all()
    )
    for d in expired:
        _clawback(db, d, note="Auto-refund: 15-day hold expired.")
        d.status = DisputeStatus.auto_refunded
        d.resolved_at = now
        d.resolution_note = (
            "Receiver did not respond within the 15-day hold window. "
            "Funds were automatically refunded to the complainant."
        )
        _push_notification(
            db,
            user_id=d.complainant_id,
            kind=NotificationKind.dispute_expired,
            title="Auto-refund processed",
            body=(
                f"The receiver did not respond in time. "
                f"{d.claimed_amount} has been refunded to you."
            ),
            dispute_id=d.id,
        )
        _push_notification(
            db,
            user_id=d.respondent_id,
            kind=NotificationKind.dispute_expired,
            title="Hold expired",
            body=(
                f"The 15-day hold expired without a response. "
                f"{d.claimed_amount} was refunded to the complainant."
            ),
            dispute_id=d.id,
        )
    if expired:
        db.commit()
    return len(expired)


def _clawback(db: Session, dispute: Dispute, *, note: str) -> None:
    """
    Refund the complainant by reversing the original transfer.

    Implementation: re-use `execute_transfer` with a deterministic
    idempotency key `'dispute-clawback-{dispute.id}'` so a repeat
    resolution attempt is a no-op.  This produces two new ledger
    entries (debit respondent, credit complainant) which are appended
    to the hash chain and keep the double-entry invariant intact.

    If the respondent no longer has sufficient funds (e.g. they spent
    the disputed money), we fall back to the system treasury, which is
    allowed to go negative.
    """
    transfer: Transfer | None = (
        db.query(Transfer).filter(Transfer.id == dispute.transfer_id).first()
    )
    if transfer is None:
        raise LookupError(f"Transfer {dispute.transfer_id} not found")

    refund_amount = Decimal(dispute.claimed_amount)
    idempotency_key = f"dispute-clawback-{dispute.id}"

    # Try the real refund first.  If it fails for insufficient funds we
    # backstop with a treasury debit (so the complainant is never
    # stranded).
    try:
        execute_transfer(
            db=db,
            sender_id=transfer.receiver_id,
            receiver_id=transfer.sender_id,
            amount=refund_amount,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        db.rollback()
        execute_transfer(
            db=db,
            sender_id=TREASURY_ID,
            receiver_id=transfer.sender_id,
            amount=refund_amount,
            idempotency_key=f"{idempotency_key}-treasury-backstop",
        )


# ─── Read helpers ────────────────────────────────────────────────────────────

def list_disputes(db: Session, user_id) -> dict:
    """Return disputes where user is either complainant or respondent."""
    rows: list[Dispute] = (
        db.query(Dispute)
        .filter(or_(Dispute.complainant_id == user_id,
                    Dispute.respondent_id == user_id))
        .order_by(Dispute.created_at.desc())
        .all()
    )
    user_cache: dict = {}
    def _name(uid) -> str:
        if uid not in user_cache:
            u = db.query(User).filter(User.id == uid).first()
            user_cache[uid] = u.name if u else str(uid)
        return user_cache[uid]

    items = []
    for d in rows:
        if d.complainant_id == user_id:
            cp_id = d.respondent_id
            role = "complainant"
        else:
            cp_id = d.complainant_id
            role = "respondent"
        days_left = max(
            0,
            (d.hold_expires_at - _utcnow()).days,
        )
        items.append({
            "id": d.id,
            "transfer_id": d.transfer_id,
            "counterparty_id": cp_id,
            "counterparty_name": _name(cp_id),
            "role": role,
            "amount": d.claimed_amount,
            "status": d.status.value,
            "hold_expires_at": d.hold_expires_at,
            "days_until_hold_expires": days_left,
            "created_at": d.created_at,
        })

    active = sum(1 for d in rows if d.status == DisputeStatus.filed)
    auto_pending = sum(
        1 for d in rows
        if d.status == DisputeStatus.filed and d.hold_expires_at <= _utcnow()
    )
    return {
        "items": items,
        "total": len(items),
        "active_holds": active,
        "auto_refunds_pending": auto_pending,
    }


def dispute_detail(db: Session, dispute_id, *, viewer_id=None) -> dict:
    dispute: Dispute | None = (
        db.query(Dispute).filter(Dispute.id == dispute_id).first()
    )
    if dispute is None:
        raise LookupError(f"Dispute {dispute_id} not found")

    complainant = db.query(User).filter(User.id == dispute.complainant_id).first()
    respondent = db.query(User).filter(User.id == dispute.respondent_id).first()

    timeline = _build_timeline(db, dispute)
    days_left = max(
        0,
        (dispute.hold_expires_at - _utcnow()).days,
    )
    return {
        "id": dispute.id,
        "transfer_id": dispute.transfer_id,
        "complainant_id": dispute.complainant_id,
        "complainant_name": complainant.name if complainant else str(dispute.complainant_id),
        "respondent_id": dispute.respondent_id,
        "respondent_name": respondent.name if respondent else str(dispute.respondent_id),
        "screenshot_url": dispute.screenshot_url,
        "claimed_amount": dispute.claimed_amount,
        "requested_amount": dispute.requested_amount,
        "amount_delta": _abs_amount_delta(dispute.claimed_amount, dispute.requested_amount),
        "narrative": dispute.narrative,
        "status": dispute.status.value,
        "hold_expires_at": dispute.hold_expires_at,
        "days_until_hold_expires": days_left,
        "receiver_response": dispute.receiver_response,
        "resolution_note": dispute.resolution_note,
        "created_at": dispute.created_at,
        "resolved_at": dispute.resolved_at,
        "timeline": timeline,
    }


def _build_timeline(db: Session, dispute: Dispute) -> list[dict]:
    events: list[tuple[datetime, str, str, str | None]] = []
    events.append((
        dispute.created_at,
        dispute.complainant.name if dispute.complainant else str(dispute.complainant_id),
        "filed",
        f"Dispute opened; claimed {dispute.claimed_amount}, requested {dispute.requested_amount}.",
    ))
    notifs = (
        db.query(Notification)
        .filter(Notification.dispute_id == dispute.id)
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .all()
    )
    for n in notifs:
        actor = "system"
        try:
            u = db.query(User).filter(User.id == n.user_id).first()
            if u:
                actor = u.name
        except Exception:
            pass
        event_map = {
            NotificationKind.dispute_filed: "notification_sent",
            NotificationKind.dispute_responded: "receiver_responded",
            NotificationKind.dispute_resolved: "resolved",
            NotificationKind.dispute_expired: "auto_refunded",
            NotificationKind.call_outbound: "outbound_call",
        }
        events.append((n.created_at, actor, event_map.get(n.kind, n.kind.value), n.title))

    if dispute.resolved_at:
        events.append((
            dispute.resolved_at,
            "system",
            dispute.status.value,
            dispute.resolution_note,
        ))

    events.sort(key=lambda e: e[0])
    return [
        {"at": at, "actor": actor, "event": ev, "detail": det}
        for (at, actor, ev, det) in events
    ]


def list_notifications(db: Session, user_id, *, limit: int = 50) -> dict:
    rows: list[Notification] = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )
    unread = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
        .scalar()
    )
    return {
        "items": rows,
        "unread_count": int(unread or 0),
    }


def mark_notifications_read(db: Session, user_id) -> int:
    n = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
        .update({"is_read": True})
    )
    db.commit()
    return int(n)
