"""AI-provider failures must reach the browser as honest, actionable HTTP
errors.

Regression cover for a real bug: with a real OpenAI key configured whose
account had no quota, every AI request raised an untranslated SDK
exception, which FastAPI turned into a bare 500 *after* CORSMiddleware —
so the response carried no `Access-Control-Allow-Origin` and the browser
reported nothing but "Failed to fetch". The Sales Lead Finder had the
identical bug; these tests exist so neither comes back.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.ai.exceptions import (
    AiProviderAuthError,
    AiProviderNotConfigured,
    AiProviderQuotaExceeded,
    AiProviderRateLimited,
    AiProviderUnavailable,
)


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "AI Error Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


class _FailingAdapter:
    """Stands in for a configured provider that fails at call time."""

    provider_name = "openai"

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def generate(self, request):  # noqa: ANN001
        raise self._error

    async def embed(self, texts):  # noqa: ANN001
        # Copilot retrieval embeds the question before it ever generates,
        # so this is the call that actually fails first.
        raise self._error


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_fragment"),
    [
        (AiProviderQuotaExceeded("no quota"), 402, "no remaining quota"),
        (AiProviderRateLimited("slow down"), 429, "rate limiting"),
        (AiProviderAuthError("bad key"), 502, "credential was rejected"),
        (AiProviderNotConfigured("nothing set"), 409, "No AI provider is configured"),
        (AiProviderUnavailable("down"), 502, "temporarily unavailable"),
    ],
)
async def test_provider_failures_become_clean_http_errors(
    client: AsyncClient,
    monkeypatch,
    error: Exception,
    expected_status: int,
    expected_fragment: str,
) -> None:
    await _signup(client, f"ai-err-{expected_status}-{id(error)}@example.com", "AI Err Org")

    import app.ai.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "build_adapter", lambda: _FailingAdapter(error))

    response = await client.post("/api/v1/ai/copilot/ask", json={"prompt": "anything"})

    assert response.status_code == expected_status, response.text
    assert expected_fragment in response.json()["error"]["message"]
    # Never a bare 500 — that is the shape that loses the CORS header and
    # surfaces to the user as "Failed to fetch".
    assert response.status_code != 500


async def test_quota_and_rate_limit_are_not_conflated(
    client: AsyncClient, monkeypatch
) -> None:
    """OpenAI returns HTTP 429 for both an exhausted balance and a genuine
    rate limit, but only one of them is worth retrying — so they must not
    produce the same message."""
    await _signup(client, "ai-err-distinct@example.com", "AI Err Distinct Org")

    import app.ai.gateway as gateway_module

    monkeypatch.setattr(
        gateway_module, "build_adapter", lambda: _FailingAdapter(AiProviderQuotaExceeded("x"))
    )
    quota = await client.post("/api/v1/ai/copilot/ask", json={"prompt": "anything"})

    monkeypatch.setattr(
        gateway_module, "build_adapter", lambda: _FailingAdapter(AiProviderRateLimited("x"))
    )
    rate = await client.post("/api/v1/ai/copilot/ask", json={"prompt": "anything"})

    assert quota.status_code == 402
    assert rate.status_code == 429
    assert quota.json()["error"]["message"] != rate.json()["error"]["message"]


def test_openai_adapter_maps_insufficient_quota_to_its_own_error() -> None:
    """The SDK reports an exhausted balance as RateLimitError; only the
    body distinguishes it, so the adapter has to look there."""
    import httpx
    import openai

    from app.ai.adapters.openai import _translated_errors

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request, json={"error": {"code": "insufficient_quota"}})

    with pytest.raises(AiProviderQuotaExceeded):
        with _translated_errors():
            raise openai.RateLimitError(
                "Error code: 429 - {'error': {'code': 'insufficient_quota'}}",
                response=response,
                body=None,
            )

    with pytest.raises(AiProviderRateLimited):
        with _translated_errors():
            raise openai.RateLimitError(
                "Error code: 429 - {'error': {'code': 'rate_limit_exceeded'}}",
                response=response,
                body=None,
            )
