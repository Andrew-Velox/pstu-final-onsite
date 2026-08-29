"""add tamper-evident hash chain to ledger_entries

Revision ID: 0002_entry_hash_chain
Revises: 0001_initial_schema
Create Date: 2026-08-29

Adds two columns to ledger_entries:
  - prev_hash  (sha256 hex of the previous entry, or 64 zeros for genesis)
  - entry_hash (sha256 hex of prev_hash + this entry's canonical content)

Adds:
  - unique index on entry_hash
  - index on prev_hash
  - composite (created_at, entry_hash) for ordered chain scans

backfill_entry_hashes() is run inline after the column add so that
existing rows are immediately part of a verifiable chain.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_entry_hash_chain"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add the columns ────────────────────────────────────────────────
    #    prev_hash is nullable initially so the ALTER TABLE doesn't fail
    #    on existing rows; we backfill in the same migration.
    op.add_column(
        "ledger_entries",
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ledger_entries",
        sa.Column("entry_hash", sa.String(length=64), nullable=False, server_default=""),
    )

    # ── 2. Indexes ────────────────────────────────────────────────────────
    op.create_index(
        "ix_ledger_entries_prev_hash",
        "ledger_entries",
        ["prev_hash"],
    )
    op.create_index(
        "ix_ledger_entries_entry_hash",
        "ledger_entries",
        ["entry_hash"],
        unique=True,
    )
    op.create_index(
        "ix_ledger_entries_chain",
        "ledger_entries",
        ["created_at", "entry_hash"],
    )

    # ── 3. Backfill existing rows in creation order ───────────────────────
    bind = op.get_bind()
    from app.services import backfill_entry_hashes

    # Use a raw Session so we don't pull the full app runtime into alembic.
    from sqlalchemy.orm import Session

    with Session(bind=bind) as session:
        rewritten = backfill_entry_hashes(session)
        session.commit()
        # `rewritten` is informational — alembic migrations don't return
        # values to callers, but it shows in the migration log.
        print(f"[0002] backfilled entry hashes for {rewritten} existing rows")

    # ── 4. Enforce NOT NULL on prev_hash now that all rows have a value ───
    op.alter_column(
        "ledger_entries",
        "prev_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_chain", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_entry_hash", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_prev_hash", table_name="ledger_entries")
    op.drop_column("ledger_entries", "entry_hash")
    op.drop_column("ledger_entries", "prev_hash")
