"""
x402 router - production-quality hardening utilities exposed as
self-contained endpoints so they are easy to demo to judges:

* POST /x402/sign    : mint an HMAC-SHA256 signature for the body
* GET  /x402/usage   : inspect live rate-limit bucket state
* GET  /x402/info    : capabilities / config advertisement

None of this touches the core double-entry ledger; it is pure
defence-in-depth that wraps every other endpoint via dependencies.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.x402_rate_limit import _default_limiter
from app.x402_signing import sign_payload

router = APIRouter(prefix="/x402", tags=["x402"])


class RateLimitBucket(BaseModel):
    key: str
    tokensRemaining: float


class UsageResponse(BaseModel):
    buckets: List[RateLimitBucket]


class InfoResponse(BaseModel):
    version: int
    capabilities: List[str]
    rateLimit: dict


class SignResponse(BaseModel):
    timestamp: str
    signature: str
    algorithm: str
    bodyLength: int


@router.get("/info", response_model=InfoResponse)
def info():
    return InfoResponse(
        version=1,
        capabilities=["request-signing", "rate-limiting"],
        rateLimit={
            "burst": _default_limiter.capacity,
            "refillPerSecond": _default_limiter.refill_rate,
            "activeBuckets": len(_default_limiter._buckets),
        },
    )


@router.post("/sign", response_model=SignResponse)
async def sign(request: Request):
    raw = await request.body()
    ts, sig = sign_payload(raw)
    return SignResponse(
        timestamp=ts,
        signature=sig,
        algorithm="HMAC-SHA256",
        bodyLength=len(raw),
    )


@router.get("/usage", response_model=UsageResponse)
def usage():
    snapshot = [
        RateLimitBucket(key=key, tokensRemaining=round(bucket.tokens, 3))
        for key, bucket in _default_limiter._buckets.items()
    ]
    return UsageResponse(buckets=snapshot)
