"""
Shared pytest configuration and fixtures.

Automatically skips all tests if PostgreSQL is unreachable,
so test collection doesn't crash in environments without a DB.
"""

import pytest
from sqlalchemy import text

from app.database import SessionLocal


def _db_is_reachable() -> bool:
    """Quick check: can we connect to Postgres?"""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception:
        return False


# Skip the entire test session if DB is down
if not _db_is_reachable():
    pytestmark = pytest.mark.skip(reason="PostgreSQL is not reachable")


@pytest.fixture(autouse=True, scope="session")
def _require_db():
    """Skip all tests if PostgreSQL is not reachable."""
    if not _db_is_reachable():
        pytest.skip("PostgreSQL is not reachable — start it and re-run tests")
