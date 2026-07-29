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


settings = Settings()
_diagnose(settings)
