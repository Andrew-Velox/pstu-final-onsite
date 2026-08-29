"""
SQLAlchemy ORM models for the money-movement double-entry ledger system.

Design invariants
─────────────────
• **No balance column anywhere.**  A user's balance is always derived by
  summing their LedgerEntry rows (credits − debits).
• **LedgerEntry is append-only** — rows are never updated or deleted.
• **All monetary amounts use Numeric(14, 2)** — never Float.
• Every completed Transfer produces exactly two LedgerEntry rows:
  one debit (sender) and one credit (receiver) for the same amount.
"""

import enum
import uuid as _uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class TransferStatus(str, enum.Enum):
    """Possible outcomes of a transfer."""
    completed = "completed"
    failed = "failed"


class EntryType(str, enum.Enum):
    """Double-entry direction."""
    debit = "debit"
    credit = "credit"


class MoneyRequestStatus(str, enum.Enum):
    """Lifecycle states of a money request."""
    pending = "pending"
    approved = "approved"
    declined = "declined"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    """
    Application user.

    There is deliberately **no** balance column.  A user's current balance
    is computed on-the-fly from their ledger entries:

        SELECT COALESCE(
            SUM(CASE WHEN entry_type = 'credit' THEN amount ELSE -amount END), 0
        ) FROM ledger_entries WHERE user_id = :uid
    """

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── relationships (for ORM convenience only) ──────────────────────────
    sent_transfers = relationship(
        "Transfer",
        back_populates="sender",
        foreign_keys="Transfer.sender_id",
    )
    received_transfers = relationship(
        "Transfer",
        back_populates="receiver",
        foreign_keys="Transfer.receiver_id",
    )
    ledger_entries = relationship("LedgerEntry", back_populates="user")
    money_requests_made = relationship(
        "MoneyRequest",
        back_populates="requester",
        foreign_keys="MoneyRequest.requester_id",
    )
    money_requests_received = relationship(
        "MoneyRequest",
        back_populates="target",
        foreign_keys="MoneyRequest.target_id",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!s} email={self.email!r}>"


# ─── Transfer ─────────────────────────────────────────────────────────────────

class Transfer(Base):
    """
    A money transfer between two users.

    ``idempotency_key`` lets clients safely retry without double-spending:
    the unique constraint will reject a duplicate insert.
    """

    __tablename__ = "transfers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
        nullable=False,
    )
    sender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    receiver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount = Column(Numeric(precision=14, scale=2), nullable=False)
    status = Column(
        Enum(TransferStatus, name="transfer_status", create_constraint=True),
        nullable=False,
    )
    idempotency_key = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── relationships ─────────────────────────────────────────────────────
    sender = relationship(
        "User",
        back_populates="sent_transfers",
        foreign_keys=[sender_id],
    )
    receiver = relationship(
        "User",
        back_populates="received_transfers",
        foreign_keys=[receiver_id],
    )
    ledger_entries = relationship("LedgerEntry", back_populates="transfer")

    def __repr__(self) -> str:
        return (
            f"<Transfer id={self.id!s} "
            f"sender={self.sender_id!s} → receiver={self.receiver_id!s} "
            f"amount={self.amount} status={self.status.value}>"
        )


# ─── LedgerEntry ──────────────────────────────────────────────────────────────

class LedgerEntry(Base):
    """
    Immutable, append-only ledger row.

    Every completed transfer creates exactly **two** entries with the same
    ``transfer_id`` and ``amount``:

    1. A *debit* against the sender (money leaves).
    2. A *credit* to the receiver (money arrives).

    The current balance of any user is:

        SUM(credit amounts) − SUM(debit amounts)
    """

    __tablename__ = "ledger_entries"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transfer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transfers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entry_type = Column(
        Enum(EntryType, name="entry_type", create_constraint=True),
        nullable=False,
    )
    amount = Column(Numeric(precision=14, scale=2), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # ── Tamper-evident hash chain ────────────────────────────────────────
    # Each entry stores the SHA-256 of the *previous* ledger entry plus its
    # own canonical content.  This is a mini-blockchain inside the table:
    # any tampering with a prior row breaks the chain at every later row.
    prev_hash = Column(String(64), nullable=True, index=True)
    entry_hash = Column(String(64), nullable=False, unique=True, index=True)

    # ── relationships ─────────────────────────────────────────────────────
    user = relationship("User", back_populates="ledger_entries")
    transfer = relationship("Transfer", back_populates="ledger_entries")

    # ── extra indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_ledger_entries_user_created", "user_id", "created_at"),
        Index("ix_ledger_entries_chain", "created_at", "entry_hash"),
    )

    def __repr__(self) -> str:
        return (
            f"<LedgerEntry id={self.id!s} user={self.user_id!s} "
            f"{self.entry_type.value} {self.amount}>"
        )


# ─── MoneyRequest ─────────────────────────────────────────────────────────────

class MoneyRequest(Base):
    """
    A request from one user (requester) asking another (target) to send money.
    """

    __tablename__ = "money_requests"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
        nullable=False,
    )
    requester_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount = Column(Numeric(precision=14, scale=2), nullable=False)
    status = Column(
        Enum(
            MoneyRequestStatus,
            name="money_request_status",
            create_constraint=True,
        ),
        default=MoneyRequestStatus.pending,
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── relationships ─────────────────────────────────────────────────────
    requester = relationship(
        "User",
        back_populates="money_requests_made",
        foreign_keys=[requester_id],
    )
    target = relationship(
        "User",
        back_populates="money_requests_received",
        foreign_keys=[target_id],
    )

    def __repr__(self) -> str:
        return (
            f"<MoneyRequest id={self.id!s} "
            f"requester={self.requester_id!s} → target={self.target_id!s} "
            f"amount={self.amount} status={self.status.value}>"
        )
