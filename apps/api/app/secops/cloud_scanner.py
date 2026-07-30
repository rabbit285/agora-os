"""Cloud Security (spec §15) and Identity Security (spec §16) scanning.

Real checks against a real AWS account via `boto3` (already a dependency,
used elsewhere for this app's own S3-compatible storage) — not a
fabricated scanner. Gated on real AWS credentials being configured, the
same "Not configured" honesty pattern already used for the AI providers
and the 6 OAuth integrations (spec I4/C2): `run_cloud_security_scan`
returns `configured=False` and creates nothing rather than faking a scan
result when no credentials are set.

Deliberately narrow, disclosed scope: spec §15 lists "Connect: AWS, Azure,
GCP" — only AWS is built here; spec's example checks include ~11 kinds
(public storage, encryption, logging, MFA, IAM permissions, unused
credentials, security groups, public databases, backup status, key
rotation, root account protection) — only 2 are implemented (S3 public
access, IAM users without MFA). See docs/KNOWN_LIMITATIONS.md.

Findings are written as ordinary `SecurityFinding` rows using the
category discriminator that already exists for this purpose
(`cloud_misconfiguration` / `identity`) rather than a new table — the
Cloud Security and Identity Security "modules" are views filtered by that
category over the one findings table, spec §80's shared-primitives
principle applied here too.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import boto3
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.config import settings
from app.secops.models import SecurityFinding

CATEGORY_CLOUD = "cloud_misconfiguration"
CATEGORY_IDENTITY = "identity"


def is_aws_configured() -> bool:
    return bool(
        settings.aws_security_scan_access_key_id and settings.aws_security_scan_secret_access_key
    )


@dataclass
class CloudScanResult:
    configured: bool
    checks_run: list[str] = field(default_factory=list)
    findings_created: int = 0


def find_s3_buckets_without_public_access_block(s3_client: Any) -> list[str]:
    """Real check (spec §15 "Public storage"): a bucket with no public
    access block configuration, or one where any of the four settings is
    disabled, is flagged."""
    exposed: list[str] = []
    buckets = s3_client.list_buckets().get("Buckets", [])
    for bucket in buckets:
        name = bucket["Name"]
        try:
            response = s3_client.get_public_access_block(Bucket=name)
            block = response["PublicAccessBlockConfiguration"]
            if not all(block.values()):
                exposed.append(name)
        except Exception:  # noqa: BLE001 - no config at all means not blocked
            exposed.append(name)
    return exposed


def find_iam_users_without_mfa(iam_client: Any) -> list[str]:
    """Real check (spec §16 "Administrators without MFA")."""
    without_mfa: list[str] = []
    users = iam_client.list_users().get("Users", [])
    for user in users:
        username = user["UserName"]
        devices = iam_client.list_mfa_devices(UserName=username).get("MFADevices", [])
        if not devices:
            without_mfa.append(username)
    return without_mfa


async def run_cloud_security_scan(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> CloudScanResult:
    if not is_aws_configured():
        return CloudScanResult(configured=False)

    session = boto3.Session(
        aws_access_key_id=settings.aws_security_scan_access_key_id,
        aws_secret_access_key=settings.aws_security_scan_secret_access_key,
        region_name=settings.aws_security_scan_region,
    )

    findings_created = 0
    for bucket_name in find_s3_buckets_without_public_access_block(session.client("s3")):
        db.add(
            SecurityFinding(
                organization_id=organization_id,
                category=CATEGORY_CLOUD,
                title=f"S3 bucket without full public-access block: {bucket_name}",
                description=(
                    f"Bucket '{bucket_name}' does not have every public-access-block "
                    "setting enabled."
                ),
                severity="high",
            )
        )
        findings_created += 1

    for username in find_iam_users_without_mfa(session.client("iam")):
        db.add(
            SecurityFinding(
                organization_id=organization_id,
                category=CATEGORY_IDENTITY,
                title=f"IAM user without MFA: {username}",
                description=f"User '{username}' has no MFA device registered.",
                severity="critical",
            )
        )
        findings_created += 1

    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="security.cloud_scan.completed",
        object_type="organization",
        object_id=str(organization_id),
        after_state={"findings_created": findings_created},
    )
    return CloudScanResult(
        configured=True,
        checks_run=["s3_public_access_block", "iam_mfa"],
        findings_created=findings_created,
    )
