"""Redis-backed rate limiting (spec §E7 "API Quality": "rate limiting").
A real, fixed-window limiter keyed by client IP (the one identity
available before authentication runs, so it also protects unauthenticated
endpoints like `/auth/login`) — not a stub that always allows every
request. Fails open on a Redis outage: availability of the rest of the
API matters more than perfect enforcement of this one cross-cutting
control, the same tradeoff `app.core.idempotency` makes.
"""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.config import settings

_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
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
        client_host = request.client.host if request.client else "unknown"
        window = int(time.time() // _WINDOW_SECONDS)
        key = f"ratelimit:{client_host}:{window}"

        try:
            redis_client = self._get_redis()
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, _WINDOW_SECONDS)
        except Exception:
            # Redis unreachable — fail open rather than take down the API.
            return await call_next(request)

        if count > settings.rate_limit_max_requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": "Rate limit exceeded. Try again shortly.",
                        "details": None,
                        "request_id": None,
                    }
                },
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )
        return await call_next(request)
