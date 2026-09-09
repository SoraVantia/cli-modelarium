"""Small helpers shared across provider modules."""

from __future__ import annotations

from typing import Any

# HTTP statuses that mean "try again shortly" rather than "this request is
# wrong". The retry loop in `streaming.py` catches `ProviderOverloadedError`
# and backs off exponentially, bounded at DEFAULT_MAX_RETRIES; these are the
# codes that should reach it.
#
# 502/503/504 are transient infrastructure states - bad gateway, service
# unavailable, gateway timeout - and 529 is Anthropic's explicit "overloaded".
# A live probe on 2026-09-06 measured gemini-3.8-flash returning 503
# "experiencing high demand" on 6 of 14 attempts; before this set existed each
# one became a dead cell at 0 tokens while the rest of the sweep was billed.
#
# 500 is deliberately absent. A generic internal error can be a deterministic
# failure of this exact request, and retrying it three times only bills the
# latency again.
TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({502, 503, 504, 529})


def extract_retry_after(error: Any) -> float | None:
    """Read a numeric `Retry-After` header from an SDK exception's response.

    Handles either case (`retry-after` or `Retry-After`). Returns None if the
    header is missing or not a parseable number (HTTP-date format is ignored).
    """
    response = getattr(error, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
