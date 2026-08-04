"""Idempotency-Key support for side-effecting requests (spec §E7 "API
Quality": "idempotency for side effects"). Opt-in: a client sends a real
`Idempotency-Key` header on a POST/PUT/PATCH/DELETE request; a retried
request with the same key, from the same session, against the same
method+path replays the exact cached response instead of re-executing
the side effect. Requests without the header are entirely unaffected —
this never changes behavior for the hundreds of existing call sites that
don't send it. Redis-backed; fails open on a Redis outage, the same
availability-over-perfect-enforcement tradeoff `app.core.rate_limit`
makes.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

_TTL_SECONDS = 24 * 60 * 60
_METHODS_WITH_SIDE_EFFECTS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self._redis: Any = None

    def _get_redis(self) -> Any:
        if self._redis is None:
            import redis.asyncio as redis

            # redis-py ships without a py.typed marker for its asyncio
            # client, the same gap boto3 has (see app.core.storage).
            self._redis = redis.from_url(  # type: ignore[no-untyped-call]
                settings.redis_url, decode_responses=True
            )
        return self._redis

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        idempotency_key = request.headers.get("idempotency-key")
        if request.method not in _METHODS_WITH_SIDE_EFFECTS or not idempotency_key:
            return await call_next(request)

        # Scoped by session identity too, not just the client-supplied key
        # — two different organizations' clients could otherwise coincide
        # on the same literal Idempotency-Key value and replay each
        # other's cached response across a tenant boundary.
        session_identity = request.cookies.get(settings.session_cookie_name, "anonymous")
        cache_key = (
            f"idempotency:{session_identity}:{request.method}:{request.url.path}:{idempotency_key}"
        )

        try:
            redis_client = self._get_redis()
            cached = await redis_client.get(cache_key)
        except Exception:
            return await call_next(request)

        if cached is not None:
            payload = json.loads(cached)
            response = Response(
                content=payload["body"],
                status_code=payload["status_code"],
                media_type=payload["media_type"],
            )
            response.headers["Idempotency-Replayed"] = "true"
            return response

        response = await call_next(request)

        if 200 <= response.status_code < 300:
            body = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body = body + (chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            with contextlib.suppress(Exception):
                await redis_client.set(
                    cache_key,
                    json.dumps(
                        {
                            "status_code": response.status_code,
                            "body": body.decode("utf-8"),
                            "media_type": response.media_type or "application/json",
                        }
                    ),
                    ex=_TTL_SECONDS,
                )
            return Response(
                content=body, status_code=response.status_code, media_type=response.media_type
            )
        return response
