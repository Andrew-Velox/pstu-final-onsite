"""
System-level endpoints — primarily the ledger-wide correctness check.

Endpoints
─────────
GET /system/health-check — sums every LedgerEntry in the database and
                            proves the double-entry invariant:
                              Σ credits − Σ debits  ==  0
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import HealthCheckResponse
from app.services import system_ledger_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health-check", response_model=HealthCheckResponse)
def health_check(db: Session = Depends(get_db)):
    """
    Provable correctness check for the double-entry ledger.

    In a healthy system every credit has an equal, offsetting debit, so
    the sum of all credit amounts minus the sum of all debit amounts
    across every user (including the treasury) must equal exactly zero.

    Returns ``ledger_is_balanced: true`` iff this invariant holds.
    """
    return HealthCheckResponse(**system_ledger_health(db))