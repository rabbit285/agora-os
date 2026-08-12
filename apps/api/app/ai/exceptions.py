"""Normalized AI-provider error model.

Mirrors `app.sales.providers.exceptions`: every adapter maps its provider's
real failures onto one of these, so callers and the HTTP layer never need
to know which SDK raised. Without this, a provider fault propagates as an
unhandled exception, which FastAPI turns into a bare 500 *after*
CORSMiddleware has already been passed — the browser then blocks the
response outright and the user sees "Failed to fetch" instead of the real
reason. The Sales Lead Finder had exactly this bug.
"""

from __future__ import annotations


class AiProviderError(Exception):
    """Base class for all AI-provider failures."""


class AiProviderNotConfigured(AiProviderError):
    """No credential is configured for the selected provider."""


class AiProviderAuthError(AiProviderError):
    """The configured credential was rejected."""


class AiProviderQuotaExceeded(AiProviderError):
    """The account is out of credit or over its plan limit. Distinct from
    a rate limit: retrying later does not help, someone has to add funds
    or raise the plan, so the message has to say so."""


class AiProviderRateLimited(AiProviderError):
    def __init__(self, detail: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


class AiProviderUnavailable(AiProviderError):
    """Transient failure: 5xx, timeout, or connection error."""
