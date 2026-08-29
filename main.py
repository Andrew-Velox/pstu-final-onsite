"""
Money Movement API — FastAPI entry point.
"""
from fastapi import FastAPI

# Import models so they are registered with Base.metadata
from app import models  # noqa: F401

app = FastAPI(
    title="Money Movement API",
    description="Double-entry ledger system for peer-to-peer money transfers.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}
