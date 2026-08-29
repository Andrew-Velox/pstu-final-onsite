"""create initial schema – users, transfers, ledger_entries, money_requests

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-29

Tables are created in FK-dependency order:
  1. users          (no foreign keys)
  2. transfers      (FK → users)
  3. ledger_entries (FK → users, FK → transfers)
  4. money_requests (FK → users)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Explicit index on email (also enforced by unique constraint)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── 2. transfers ─────────────────────────────────────────────────────
    # Create the enum type first
    transfer_status_enum = sa.Enum(
        "completed", "failed", name="transfer_status", create_type=True
    )

    op.create_table(
        "transfers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "sender_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "receiver_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", transfer_status_enum, nullable=False),
        sa.Column(
            "idempotency_key",
            sa.String(255),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_transfers_idempotency_key",
        "transfers",
        ["idempotency_key"],
        unique=True,
    )

    # ── 3. ledger_entries ────────────────────────────────────────────────
    entry_type_enum = sa.Enum(
        "debit", "credit", name="entry_type", create_type=True
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transfer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("transfers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entry_type", entry_type_enum, nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Fast balance / history lookups by user
    op.create_index(
        "ix_ledger_entries_user_id",
        "ledger_entries",
        ["user_id"],
    )
    # Composite index for paginated history queries
    op.create_index(
        "ix_ledger_entries_user_created",
        "ledger_entries",
        ["user_id", "created_at"],
    )

    # ── 4. money_requests ────────────────────────────────────────────────
    money_request_status_enum = sa.Enum(
        "pending", "approved", "declined",
        name="money_request_status",
        create_type=True,
    )

    op.create_table(
        "money_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "requester_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "status",
            money_request_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("money_requests")
    op.drop_table("ledger_entries")
    op.drop_table("transfers")
    op.drop_table("users")

    # Clean up enum types
    sa.Enum(name="money_request_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="entry_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transfer_status").drop(op.get_bind(), checkfirst=True)
