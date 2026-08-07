"""Normalized provider error model (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §3) — every adapter maps its
provider's real HTTP/network errors onto one of these so callers (the
search/enrichment services, the router's error responses) never need to
know which specific provider raised."""

from __future__ import annotations


class SalesProviderError(Exception):
    """Base class for all Sales data-provider failures."""


class ProviderNotConfigured(SalesProviderError):
    """No credential is configured for this provider."""


class ProviderRateLimited(SalesProviderError):
    def __init__(self, detail: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


class ProviderAuthError(SalesProviderError):
    """Credentials are configured but were rejected — must never look
    identical to "never configured" (an authored, once-working key that's
    since been revoked is a `Failed` state, not `Not configured`).

    Carries the provider's real status code (401 vs. 403) so callers can
    distinguish "bad credential" from "credential valid but lacks access
    to this capability/plan" rather than collapsing both into one message.
    """

    def __init__(self, detail: str, status_code: int = 401) -> None:
        super().__init__(detail)
        self.status_code = status_code


class ProviderInvalidRequest(SalesProviderError):
    """The provider rejected the request itself as malformed/unsupported
    (HTTP 422) — a filter or field this adapter's normalization sent that
    the provider's API doesn't accept, not a credential problem."""


class ProviderUnavailable(SalesProviderError):
    """Transient failure: 5xx, timeout, or connection error."""


class ProviderCapabilityUnsupported(SalesProviderError):
    """Raised when a caller invokes a capability this provider's own
    `capabilities()` already reported as unsupported — a programming
    error in the caller, not a runtime provider failure."""
