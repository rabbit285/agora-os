"""Short-TTL search-result cache (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §8). Redis-backed, fails open on
a Redis outage — the same availability-over-perfect-caching tradeoff
`app.core.rate_limit` and `app.core.idempotency` make; a cache miss just
means the real provider call runs, never a hard failure.

Tenant isolation is structural: `organization_id` is part of the cache
key itself, so a cross-tenant read is a different key, not an
access-control check that could be bypassed.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

from app.config import settings

TTL_SECONDS = 300

_redis: Any = None


def _get_redis() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as redis

        # redis-py ships without a py.typed marker for its asyncio client
        # (see app.core.storage / app.core.rate_limit for the same note).
        _redis = redis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    return _redis


def _filters_digest(filters: Any) -> str:
    payload = json.dumps(asdict(filters), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_cache_key(
    *,
    organization_id: uuid.UUID,
    provider: str,
    record_type: str,
    filters: Any,
    page: int,
    sort_key: str | None,
) -> str:
    return (
        f"sales:search:{organization_id}:{provider}:{record_type}:"
        f"{_filters_digest(filters)}:{page}:{sort_key or '-'}"
    )


async def get_cached(key: str) -> dict[str, Any] | None:
    try:
        client = _get_redis()
        raw = await client.get(key)
    except Exception:
        return None
    if raw is None:
        return None
    result: dict[str, Any] = json.loads(raw)
    return result


async def set_cached(key: str, value: dict[str, Any]) -> None:
    try:
        client = _get_redis()
        await client.set(key, json.dumps(value, default=str), ex=TTL_SECONDS)
    except Exception:
        # Cache write failures never block returning the real result to
        # the caller — see module docstring.
        return
