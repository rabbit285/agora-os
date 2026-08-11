"""Typed environment configuration with startup diagnostics.

Per docs/ENVIRONMENT_VARIABLES.md and the spec's "C. Secrets and .env
Contract": the app must boot without paid third-party API keys, and missing
variables are reported by name only — never by value.
"""

from __future__ import annotations

import logging
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("agora.config")


class Settings(BaseSettings):
    # ".env.local" is read second so it overrides ".env" — the standard
    # local-override convention (spec §C "Secrets and .env Contract"); both
    # are gitignored, neither is ever built into a Docker image (see
    # infra/docker/Dockerfile.api's explicit COPY list) or deployed to AWS,
    # where config instead comes from Secrets Manager/Parameter Store (see
    # docs/ENVIRONMENT_VARIABLES.md).
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    # Core
    app_env: str = Field(default="development", alias="APP_ENV")
    app_url: str = Field(default="http://localhost:3000", alias="APP_URL")
    api_url: str = Field(default="http://localhost:8000", alias="API_URL")
    secret_key: str = Field(default="dev-insecure-secret-change-me", alias="SECRET_KEY")
    database_url: str = Field(
        default="postgresql+psycopg://agora:agora@localhost:5432/agora",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    # spec §E7 "API Quality": rate limiting. Real Redis-backed per-IP fixed-
    # window cap (app.core.rate_limit) — the test suite overrides this to a
    # very high number (see tests/conftest.py) since it issues thousands of
    # requests from one loopback identity, which a production-tuned limit
    # would otherwise trip; tests/test_rate_limit.py monkeypatches it back
    # down to prove real enforcement.
    rate_limit_max_requests_per_minute: int = Field(
        default=300, alias="RATE_LIMIT_MAX_REQUESTS_PER_MINUTE"
    )

    # Temporal
    temporal_address: str = Field(default="localhost:7233", alias="TEMPORAL_ADDRESS")
    temporal_namespace: str = Field(default="default", alias="TEMPORAL_NAMESPACE")
    temporal_deployment_mode: str = Field(default="local", alias="TEMPORAL_DEPLOYMENT_MODE")

    # Object storage
    s3_endpoint_url: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT_URL")
    # Used only for presigned URLs handed to the browser — inside Docker,
    # S3_ENDPOINT_URL is an internal hostname (e.g. "http://minio:9000")
    # the browser can't resolve. Defaults to S3_ENDPOINT_URL for non-Docker
    # setups where both are already browser-reachable.
    s3_public_endpoint_url: str | None = Field(default=None, alias="S3_PUBLIC_ENDPOINT_URL")
    s3_bucket: str = Field(default="agora-local", alias="S3_BUCKET")
    s3_access_key_id: str = Field(default="agora", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="agora-secret", alias="S3_SECRET_ACCESS_KEY")
    s3_region: str = Field(default="eu-central-1", alias="S3_REGION")

    # Auth / sessions
    session_cookie_name: str = Field(default="agora_session", alias="SESSION_COOKIE_NAME")
    session_ttl_hours: int = Field(default=24 * 14, alias="SESSION_TTL_HOURS")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")

    # AI providers — optional; absence triggers the demo adapter, never a crash
    ai_provider: str = Field(default="demo", alias="AI_PROVIDER")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Email — optional; absence disables outbound email, never crashes the app
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    ses_region: str | None = Field(default=None, alias="SES_REGION")

    # Cloud Security scanning (spec §15) — optional; absence means Cloud
    # Security / Identity Security report "Not configured" rather than a
    # fake scan result. Deliberately separate from S3_* above, which point
    # at this app's own MinIO/S3 object storage, not a customer AWS
    # account to scan.
    aws_security_scan_access_key_id: str | None = Field(
        default=None, alias="AWS_SECURITY_SCAN_ACCESS_KEY_ID"
    )
    aws_security_scan_secret_access_key: str | None = Field(
        default=None, alias="AWS_SECURITY_SCAN_SECRET_ACCESS_KEY"
    )
    aws_security_scan_region: str = Field(default="eu-central-1", alias="AWS_SECURITY_SCAN_REGION")

    # Sales company enrichment (spec §21) — optional; absence means
    # Enrichment reports configured=false rather than a fabricated
    # company profile.
    clearbit_api_key: str | None = Field(default=None, alias="CLEARBIT_API_KEY")

    # Sales Lead Finder's external company/people discovery provider (see
    # docs/SALES_DATA_PROVIDER_ARCHITECTURE.md and
    # docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md).
    #
    # Production uses per-customer OAuth connections, never this key: each
    # organization connects its own Apollo workspace and Agora Origin calls
    # Apollo with that customer's Bearer token, permissions, limits, and
    # credits. `APOLLO_API_KEY` survives only for the isolated
    # `APOLLO_AUTH_MODE=api_key` local-development/test mode below, and
    # `_diagnose` refuses to start a production process that enables it.
    apollo_api_key: str | None = Field(default=None, alias="APOLLO_API_KEY")
    # "oauth" (default, and the only value permitted in production) |
    # "api_key" (development/test only — a single shared credential must
    # never serve multi-tenant production traffic).
    apollo_auth_mode: str = Field(default="oauth", alias="APOLLO_AUTH_MODE")
    apollo_oauth_client_id: str | None = Field(default=None, alias="APOLLO_OAUTH_CLIENT_ID")
    apollo_oauth_client_secret: str | None = Field(default=None, alias="APOLLO_OAUTH_CLIENT_SECRET")
    apollo_oauth_redirect_uri: str | None = Field(default=None, alias="APOLLO_OAUTH_REDIRECT_URI")
    # Non-secret provider endpoints, centralized so a future Apollo change
    # is a config edit rather than a code change.
    apollo_oauth_authorize_url: str = Field(
        default="https://app.apollo.io/#/oauth/authorize", alias="APOLLO_OAUTH_AUTHORIZE_URL"
    )
    apollo_oauth_token_url: str = Field(
        default="https://app.apollo.io/api/v1/oauth/token", alias="APOLLO_OAUTH_TOKEN_URL"
    )
    apollo_api_base_url: str = Field(
        default="https://api.apollo.io/api/v1", alias="APOLLO_API_BASE_URL"
    )

    # Billing — optional
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_publishable_key: str | None = Field(default=None, alias="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")

    # Integrations — optional; absence means the connector's catalog entry
    # reports configured=false and no real OAuth flow can start (never a
    # fake "connected" state, spec §82). Every provider follows the same
    # three-variable shape (CLIENT_ID/CLIENT_SECRET/REDIRECT_URI) so adding
    # a seventh provider later is a config+adapter addition, not a
    # structural change — see `app/integrations/adapters/__init__.py` and
    # `docs/DECISIONS.md` ADR-0028.
    hubspot_client_id: str | None = Field(default=None, alias="HUBSPOT_CLIENT_ID")
    hubspot_client_secret: str | None = Field(default=None, alias="HUBSPOT_CLIENT_SECRET")
    hubspot_redirect_uri: str | None = Field(default=None, alias="HUBSPOT_REDIRECT_URI")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str | None = Field(default=None, alias="GOOGLE_REDIRECT_URI")
    microsoft_client_id: str | None = Field(default=None, alias="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: str | None = Field(default=None, alias="MICROSOFT_CLIENT_SECRET")
    microsoft_redirect_uri: str | None = Field(default=None, alias="MICROSOFT_REDIRECT_URI")
    github_client_id: str | None = Field(default=None, alias="GITHUB_CLIENT_ID")
    github_client_secret: str | None = Field(default=None, alias="GITHUB_CLIENT_SECRET")
    github_redirect_uri: str | None = Field(default=None, alias="GITHUB_REDIRECT_URI")
    slack_client_id: str | None = Field(default=None, alias="SLACK_CLIENT_ID")
    slack_client_secret: str | None = Field(default=None, alias="SLACK_CLIENT_SECRET")
    slack_redirect_uri: str | None = Field(default=None, alias="SLACK_REDIRECT_URI")
    salesforce_client_id: str | None = Field(default=None, alias="SALESFORCE_CLIENT_ID")
    salesforce_client_secret: str | None = Field(default=None, alias="SALESFORCE_CLIENT_SECRET")
    salesforce_redirect_uri: str | None = Field(default=None, alias="SALESFORCE_REDIRECT_URI")
    zendesk_client_id: str | None = Field(default=None, alias="ZENDESK_CLIENT_ID")
    zendesk_client_secret: str | None = Field(default=None, alias="ZENDESK_CLIENT_SECRET")
    zendesk_redirect_uri: str | None = Field(default=None, alias="ZENDESK_REDIRECT_URI")
    # Known simplification (see docs/KNOWN_LIMITATIONS.md): unlike the other
    # five providers, a Zendesk OAuth app is registered against one
    # customer's subdomain (there is no single multi-tenant authorize URL),
    # so this build supports exactly one configured Zendesk account rather
    # than a per-connection subdomain prompt a production build would add.
    zendesk_subdomain: str | None = Field(default=None, alias="ZENDESK_SUBDOMAIN")
    pipedrive_client_id: str | None = Field(default=None, alias="PIPEDRIVE_CLIENT_ID")
    pipedrive_client_secret: str | None = Field(default=None, alias="PIPEDRIVE_CLIENT_SECRET")
    pipedrive_redirect_uri: str | None = Field(default=None, alias="PIPEDRIVE_REDIRECT_URI")
    intercom_client_id: str | None = Field(default=None, alias="INTERCOM_CLIENT_ID")
    intercom_client_secret: str | None = Field(default=None, alias="INTERCOM_CLIENT_SECRET")
    intercom_redirect_uri: str | None = Field(default=None, alias="INTERCOM_REDIRECT_URI")
    # Encrypts stored OAuth tokens at rest (app/core/crypto.py). Falls back
    # to a key derived from SECRET_KEY when unset — fine for dev/test,
    # a real deployment should set its own (see docs/KNOWN_LIMITATIONS.md).
    token_encryption_key: str | None = Field(default=None, alias="TOKEN_ENCRYPTION_KEY")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def s3_public_endpoint_url_resolved(self) -> str:
        return self.s3_public_endpoint_url or self.s3_endpoint_url


def _diagnose(settings: Settings) -> None:
    """Log which optional integrations are configured vs not, by name only."""
    optional_flags = {
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "OPENAI_API_KEY": settings.openai_api_key,
        "SMTP_HOST": settings.smtp_host,
        "STRIPE_SECRET_KEY": settings.stripe_secret_key,
        "HUBSPOT_CLIENT_ID": settings.hubspot_client_id,
        "GOOGLE_CLIENT_ID": settings.google_client_id,
        "MICROSOFT_CLIENT_ID": settings.microsoft_client_id,
        "GITHUB_CLIENT_ID": settings.github_client_id,
        "SLACK_CLIENT_ID": settings.slack_client_id,
        "SALESFORCE_CLIENT_ID": settings.salesforce_client_id,
        "ZENDESK_CLIENT_ID": settings.zendesk_client_id,
        "PIPEDRIVE_CLIENT_ID": settings.pipedrive_client_id,
        "INTERCOM_CLIENT_ID": settings.intercom_client_id,
        "AWS_SECURITY_SCAN_ACCESS_KEY_ID": settings.aws_security_scan_access_key_id,
        "CLEARBIT_API_KEY": settings.clearbit_api_key,
        "APOLLO_OAUTH_CLIENT_ID": settings.apollo_oauth_client_id,
    }
    missing = [name for name, value in optional_flags.items() if not value]
    if missing:
        logger.info(
            "Optional integrations not configured (features degrade gracefully): %s",
            ", ".join(missing),
        )
    if settings.is_production and settings.secret_key == "dev-insecure-secret-change-me":
        logger.error("SECRET_KEY is unset in a production environment. Refusing to start.")
        sys.exit(1)
    # A single shared Apollo key must never supply data to multiple
    # customers (docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §7): in
    # production every organization uses its own OAuth connection, spending
    # its own Apollo credits under its own permissions.
    if settings.is_production and settings.apollo_auth_mode != "oauth":
        logger.error(
            "APOLLO_AUTH_MODE=%s is not permitted in production — customer-connected "
            "OAuth is required so each organization uses its own Apollo account. "
            "Refusing to start.",
            settings.apollo_auth_mode,
        )
        sys.exit(1)
    if settings.apollo_auth_mode not in ("oauth", "api_key"):
        logger.error(
            "APOLLO_AUTH_MODE must be 'oauth' or 'api_key' (got '%s'). Refusing to start.",
            settings.apollo_auth_mode,
        )
        sys.exit(1)


settings = Settings()
_diagnose(settings)
