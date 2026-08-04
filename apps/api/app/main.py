from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.billing.service import ensure_plan_catalog
from app.config import settings
from app.core.idempotency import IdempotencyKeyMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.rbac import ensure_system_roles
from app.core.storage import ensure_bucket
from app.db.session import AsyncSessionLocal
from app.identity.router import router as auth_router
from app.routers import (
    ai,
    approvals,
    automation,
    billing,
    briefing,
    compliance,
    files,
    health,
    integrations,
    knowledge,
    notifications,
    onboarding,
    organizations,
    recommendations,
    reporting,
    sales,
    search,
    security,
    support,
    tasks,
    trust_center,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Local/dev convenience only — a real AWS deployment provisions the
    # bucket via Terraform (docs/PLATFORM_ARCHITECTURE.md), not at boot.
    ensure_bucket()
    # Re-syncs system roles/permissions on every boot (ensure_system_roles
    # is additive-only — see its docstring) so a newly added PERMISSIONS
    # entry or ROLE_PERMISSION_GRANTS line reaches already-seeded system
    # roles in a running deployment without a separate manual seed step.
    async with AsyncSessionLocal() as db:
        await ensure_system_roles(db)
        await ensure_plan_catalog(db)
    yield


app = FastAPI(title="Agora Origin API", version="0.1.0", lifespan=lifespan)

# spec §E7 "API Quality": rate limiting and idempotency for side effects.
# Both fail open on a Redis outage. Added before CORSMiddleware: Starlette
# wraps whichever middleware is added *last* as the outermost layer, so
# CORS — added last, below — stays outermost and still attaches its
# headers to a 429 or a replayed response, rather than those short-circuit
# responses bypassing CORS entirely and surfacing to the browser as an
# opaque CORS failure instead of the real error.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


def _error_envelope(
    request: Request, status_code: int, message: str, details: object = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_envelope(request, exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Pydantic v2 includes the raw exception instance in each error's `ctx`
    # for a custom `@field_validator` that raises `ValueError` (e.g.
    # app.onboarding.schemas.GoalsStepUpdate, app.automation.schemas.
    # WorkflowCreate) — stdlib `json.dumps` can't serialize that, so every
    # such validator previously 500'd instead of returning the intended
    # 422. `jsonable_encoder` is FastAPI's own sanitizer for exactly this.
    return _error_envelope(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Validation error",
        jsonable_encoder(exc.errors()),
    )


app.include_router(health.router)
app.include_router(auth_router)
app.include_router(organizations.router)
app.include_router(billing.router)
app.include_router(onboarding.router)
app.include_router(tasks.router)
app.include_router(approvals.router)
app.include_router(files.router)
app.include_router(notifications.router)
app.include_router(ai.router)
app.include_router(knowledge.router)
app.include_router(compliance.router)
app.include_router(security.router)
app.include_router(sales.router)
app.include_router(support.router)
app.include_router(automation.router)
app.include_router(integrations.router)
app.include_router(trust_center.router)
app.include_router(search.router)
app.include_router(reporting.router)
app.include_router(recommendations.router)
app.include_router(briefing.router)
