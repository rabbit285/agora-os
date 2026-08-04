"""Tests for spec §E7 "API Quality": real, Redis-backed rate limiting
(`app.core.rate_limit`) and Idempotency-Key support for side effects
(`app.core.idempotency`). Both middlewares are opt-in-by-default no-ops
for the hundreds of existing call sites that never trip them (the full
suite runs with a very high rate-limit ceiling — see conftest.py — and
idempotency only ever activates when a caller sends the header), so
these tests exercise the real enforcement paths directly rather than
relying on incidental traffic.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "API Quality Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def _flush_rate_limit_keys() -> None:
    import redis.asyncio as redis

    from app.config import settings

    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    async for key in redis_client.scan_iter("ratelimit:*"):
        await redis_client.delete(key)
    await redis_client.aclose()


async def test_rate_limit_blocks_requests_once_the_per_minute_cap_is_exceeded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    await _flush_rate_limit_keys()
    monkeypatch.setattr(settings, "rate_limit_max_requests_per_minute", 2)

    first = await client.get("/health")
    second = await client.get("/health")
    third = await client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers.get("Retry-After") is not None
    assert third.json()["error"]["message"]


async def test_rate_limit_response_still_carries_cors_headers(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 429 short-circuits before reaching the route, but CORS is the
    outermost middleware (see app.main) so its headers still apply — a
    browser client sees the real 429, not an opaque CORS failure."""
    from app.config import settings

    await _flush_rate_limit_keys()
    monkeypatch.setattr(settings, "rate_limit_max_requests_per_minute", 1)

    await client.get("/health", headers={"Origin": settings.app_url})
    blocked = await client.get("/health", headers={"Origin": settings.app_url})

    assert blocked.status_code == 429
    assert blocked.headers.get("access-control-allow-origin") == settings.app_url


async def test_idempotency_key_replays_the_cached_response_without_a_second_side_effect(
    client: AsyncClient,
) -> None:
    await _signup(client, "idem1@example.com", "Idempotency Org 1")
    key = str(uuid.uuid4())

    first = await client.post(
        "/api/v1/tasks",
        json={"title": "Follow up with prospect"},
        headers={"Idempotency-Key": key},
    )
    second = await client.post(
        "/api/v1/tasks",
        json={"title": "Follow up with prospect"},
        headers={"Idempotency-Key": key},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("idempotency-replayed") == "true"

    tasks = await client.get("/api/v1/tasks")
    assert len(tasks.json()) == 1


async def test_requests_without_an_idempotency_key_are_never_deduplicated(
    client: AsyncClient,
) -> None:
    await _signup(client, "idem2@example.com", "Idempotency Org 2")

    await client.post("/api/v1/tasks", json={"title": "Task A"})
    await client.post("/api/v1/tasks", json={"title": "Task A"})

    tasks = await client.get("/api/v1/tasks")
    assert len(tasks.json()) == 2


async def test_a_different_idempotency_key_is_not_deduplicated(client: AsyncClient) -> None:
    await _signup(client, "idem3@example.com", "Idempotency Org 3")

    await client.post(
        "/api/v1/tasks",
        json={"title": "Task A"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Task A"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    tasks = await client.get("/api/v1/tasks")
    assert len(tasks.json()) == 2
