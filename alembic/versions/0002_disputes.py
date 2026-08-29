"""add disputes and notifications tables

Revision ID: 0002_disputes
Revises: 0001_initial_schema
Create Date: 2026-08-29

Adds two new tables:

  - disputes
      Sender-side challenge against a single transfer.  Captures the
      screenshot URL, claimed vs. requested amount, hold-expires_at,
      and a status enum that drives the 15-day refund lifecycle.

  - notifications
      In-app inbox used by the Dispute Center to surface every state
      transition.  ``kind=call_outbound`` rows double as the simulated
      voice-call log.

Both tables use UUID primary keys, FKs to ``users`` / ``transfers`` /
``disputes`` with ON DELETE CASCADE/RESTRICT as appropriate, and the
standard timestamps.  An enum type per column is created at the
Postgres level by SQLAlchemy when Alembic runs.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_disputes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── disputes ─────────────────────────────────────────────────────────
    op.create_table(
        "disputes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "transfer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transfers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "complainant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "respondent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("screenshot_url", sa.String(length=1024), nullable=False),
        sa.Column("claimed_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("requested_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("narrative", sa.String(length=2000), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "filed",
                "under_review",
                "resolved_for_sender",
                "resolved_for_receiver",
                "auto_refunded",
                "rejected",
                name="dispute_status",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receiver_response", sa.String(length=2000), nullable=True),
        sa.Column("resolution_note", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_disputes_transfer_id", "disputes", ["transfer_id"])
    op.create_index("ix_disputes_complainant_id", "disputes", ["complainant_id"])
    op.create_index("ix_disputes_respondent_id", "disputes", ["respondent_id"])
    op.create_index("ix_disputes_status", "disputes", ["status"])
    op.create_index("ix_disputes_hold_expires_at", "disputes", ["hold_expires_at"])
    op.create_index(
        "ix_disputes_status_expires",
        "disputes",
        ["status", "hold_expires_at"],
    )

    # ─── notifications ────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "dispute_filed",
                "dispute_responded",
                "dispute_resolved",
                "dispute_expired",
                "call_outbound",
                name="notification_kind",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column(
            "dispute_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("disputes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_dispute_id", "notifications", ["dispute_id"])
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "is_read", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_dispute_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    sa.Enum(name="notification_kind").drop(op.get_bind(), checkfirst=False)

    op.drop_index("ix_disputes_status_expires", table_name="disputes")
    op.drop_index("ix_disputes_hold_expires_at", table_name="disputes")
    op.drop_index("ix_disputes_status", table_name="disputes")
    op.drop_index("ix_disputes_respondent_id", table_name="disputes")
    op.drop_index("ix_disputes_complainant_id", table_name="disputes")
    op.drop_index("ix_disputes_transfer_id", table_name="disputes")
    op.drop_table("disputes")
    sa.Enum(name="dispute_status").drop(op.get_bind(), checkfirst=False)