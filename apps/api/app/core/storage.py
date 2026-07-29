"""Signed-URL object storage helper (S3-compatible; MinIO locally).

Files are never served through the API process itself, and object keys are
never treated as authorization — the download URL is a short-lived signed
URL generated per request, checked against RBAC/tenant context first
(see app.routers.files).
"""

from __future__ import annotations

import uuid
from typing import Any

import boto3
from botocore.config import Config

from app.config import settings

_UPLOAD_URL_TTL_SECONDS = 300
_DOWNLOAD_URL_TTL_SECONDS = 300


def _client() -> Any:
    # boto3 ships without a py.typed marker, so its client has no static
    # type; every caller below coerces the result explicitly instead of
    # letting Any leak through this module's typed public functions.
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def _public_client() -> Any:
    # Signed URLs are handed to the browser, which cannot resolve the
    # internal Docker hostname used by _client(); this client signs against
    # the browser-reachable endpoint instead (see config.py). SigV4 signs
    # whatever host the request is actually sent to, so this is a valid
    # signature for that host, not a mismatch.
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_public_endpoint_url_resolved,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def build_storage_key(organization_id: uuid.UUID, filename: str) -> str:
    return f"org/{organization_id}/{uuid.uuid4()}/{filename}"


def presign_upload(storage_key: str, content_type: str) -> str:
    url = _public_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": storage_key, "ContentType": content_type},
        ExpiresIn=_UPLOAD_URL_TTL_SECONDS,
    )
    return str(url)


def presign_download(storage_key: str) -> str:
    url = _public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": storage_key},
        ExpiresIn=_DOWNLOAD_URL_TTL_SECONDS,
    )
    return str(url)


def download_object(storage_key: str) -> bytes:
    """Server-side direct download (no signed URL) — used by the worker's
    ingestion activity, which needs the actual bytes, not a browser-facing
    link."""
    response = _client().get_object(Bucket=settings.s3_bucket, Key=storage_key)
    body: bytes = response["Body"].read()
    return body


def upload_object(storage_key: str, data: bytes, content_type: str) -> None:
    """Server-side direct upload — used by the seed script to populate a
    real sample document without round-tripping through a signed URL."""
    _client().put_object(
        Bucket=settings.s3_bucket, Key=storage_key, Body=data, ContentType=content_type
    )


def ensure_bucket() -> None:
    """Idempotently create the configured bucket. Called at worker/dev
    startup for the local MinIO target; a real AWS deployment provisions
    the bucket via Terraform instead (docs/PLATFORM_ARCHITECTURE.md)."""
    client = _client()
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in existing:
        client.create_bucket(Bucket=settings.s3_bucket)
