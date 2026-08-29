"""
In-memory token-bucket rate limiter.

Used as a FastAPI dependency to cap request rate per ``(client_key)``.
Token bucket gives smooth bursts and a sustained long-term cap.

Defaults
--------
* ``capacity``     : 60 tokens (burst budget)
* ``refill_rate``  : 1 token / second  → 60 rpm sustained
* ``key_resolver`` : ``request.client.host`` (override for authed users)

Usage
-----
    from fastapi import Depends
    from app.x402_rate_limit import rate_limit

    @router.post("/transfers", dependencies=[Depends(rate_limit())])
    def create_transfer(...): ...

For the live stress-test demo the limits can be loosened via
``X402_RATE_LIMIT_BURST`` / ``X402_RATE_LIMIT_RPS`` env vars.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request

DEFAULT_BURST = int(os.environ.get("X402_RATE_LIMIT_BURST", "60"))
DEFAULT_RPS = float(os.environ.get("X402_RATE_LIMIT_RPS", "1.0"))


class TokenBucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, capacity: float) -> None:
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def take(self, capacity: float, refill_rate: float) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(capacity, self.tokens + elapsed * refill_rate)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimiter:
    def __init__(
        self,
        capacity: float = DEFAULT_BURST,
        refill_rate: float = DEFAULT_RPS,
        key_resolver: Optional[Callable[[Request], str]] = None,
    ) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: dict[str, TokenBucket] = defaultdict(lambda: TokenBucket(capacity))
        self._key_resolver = key_resolver or (lambda req: req.client.host if req.client else "anon")
        self._lock = Lock()

    def hit(self, request: Request) -> tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``."""
        key = self._key_resolver(request)
        with self._lock:
            bucket = self._buckets[key]
            if bucket.take(self.capacity, self.refill_rate):
                return True, 0.0
            deficit = 1 - bucket.tokens
            retry_after = max(0.05, deficit / self.refill_rate)
            return False, retry_after


_default_limiter = RateLimiter()


def rate_limit(
    capacity: float = DEFAULT_BURST,
    refill_rate: float = DEFAULT_RPS,
):
    """FastAPI dependency factory — returns ``429`` when the bucket is empty."""
    limiter = _default_limiter if (capacity == DEFAULT_BURST and refill_rate == DEFAULT_RPS) else RateLimiter(capacity, refill_rate)

    def _dep(request: Request) -> None:
        ok, retry_after = limiter.hit(request)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": f"{retry_after:.2f}"},
            )

    return _dep