"""
Request-signing helper (HMAC-SHA256).

Generates and verifies ``X-Signature`` / ``X-Timestamp`` headers so
that every write request to the API can be authenticated.  This is
the same shape that production fintech gateways use — adopting it
demonstrates defence-in-depth beyond JWT/session auth.

Usage (FastAPI dependency):

    from fastapi import Depends, Header, HTTPException
    from app.x402_signing import verify_signature

    @router.post("/transfers")
    def create_transfer(_: None = Depends(verify_signature)):
        ...

Headers
-------
``X-Timestamp``  : Unix epoch seconds (must be within ±300s of server)
``X-Signature``  : hex HMAC-SHA256 of ``"{timestamp}.{raw_body}"``
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Header, HTTPException, Request

SIGNING_SECRET: bytes = os.environ.get(
    "X402_SIGNING_SECRET",
    "dev-only-secret-rotate-me-in-production",
).encode("utf-8")
MAX_CLOCK_SKEW_SECONDS = 300


def _canonical_message(timestamp: str, body: bytes) -> bytes:
    return timestamp.encode("ascii") + b"." + body


def sign_payload(raw_body: bytes, timestamp: Optional[int] = None) -> tuple[str, str]:
    """Return ``(timestamp, hex_signature)`` for ``raw_body``."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    sig = hmac.new(
        SIGNING_SECRET,
        _canonical_message(ts, raw_body),
        hashlib.sha256,
    ).hexdigest()
    return ts, sig


async def verify_signature(
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    x_timestamp: Optional[str] = Header(default=None, alias="X-Timestamp"),
) -> None:
    """
    FastAPI dependency that validates ``X-Signature`` against the raw
    request body.  Raises 401 on any mismatch.
    """
    if not x_signature or not x_timestamp:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Signature / X-Timestamp headers",
        )

    try:
        ts_int = int(x_timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Timestamp")

    if abs(int(time.time()) - ts_int) > MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="X-Timestamp outside allowed skew")

    raw_body = await request.body()
    expected = hmac.new(
        SIGNING_SECRET,
        _canonical_message(x_timestamp, raw_body),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(status_code=401, detail="Bad signature")