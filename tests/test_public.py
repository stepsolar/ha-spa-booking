"""The website API: rate limiting and what a voucher lookup reveals."""

from __future__ import annotations

from custom_components.spa_booking.public import RateLimiter


def test_rate_limiter_blocks_then_recovers() -> None:
    limiter = RateLimiter({"voucher": 3}, window=60)
    assert all(limiter.allow("voucher", "1.2.3.4", now=t) for t in (0, 1, 2))
    assert not limiter.allow("voucher", "1.2.3.4", now=3)
    assert limiter.allow("voucher", "5.6.7.8", now=3)  # another address
    assert limiter.allow("voucher", "1.2.3.4", now=61)  # window moved on


def test_rate_limiter_kinds_are_separate() -> None:
    limiter = RateLimiter({"voucher": 1, "read": 1}, window=60)
    assert limiter.allow("voucher", "a", now=0)
    assert limiter.allow("read", "a", now=0)
    assert not limiter.allow("voucher", "a", now=1)
