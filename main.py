"""
Money Movement API — FastAPI entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import models so they are registered with Base.metadata
from app import models  # noqa: F401
from app.database import SessionLocal
from app.routers.requests import router as requests_router
from app.routers.system import router as system_router
from app.routers.transfers import router as transfers_router
from app.routers.users import router as users_router
from app.services import seed_treasury

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App startup / shutdown.

    On startup we ensure the system treasury User row exists so that
    user registrations have an account to debit from.  ``seed_treasury``
    is idempotent — it is a no-op once the row is present.
    """
    db = SessionLocal()
    try:
        seed_treasury(db)
        db.commit()
        logger.info("System treasury seeded")
    except Exception:
        db.rollback()
        logger.exception("Failed to seed treasury on startup")
    finally:
        db.close()
    yield
    # Shutdown: nothing to clean up.


app = FastAPI(
    title="Money Movement API",
    description="Double-entry ledger system for peer-to-peer money transfers.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transfers_router)
app.include_router(requests_router)
app.include_router(users_router)
app.include_router(system_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
