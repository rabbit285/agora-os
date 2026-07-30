from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.cloud_scanner import (
    find_iam_users_without_mfa,
    find_s3_buckets_without_public_access_block,
    is_aws_configured,
    run_cloud_security_scan,
)
from app.secops.models import SecurityFinding


class FakeS3Client:
    """Duck-typed stand-in for boto3's S3 client — no live AWS/moto needed
    since only the two methods the scanner actually calls are exercised."""

    def __init__(self, buckets: list[str], configs: dict[str, dict[str, bool] | None]) -> None:
        self._buckets = buckets
        # None means "no public-access-block configuration at all" (raises,
        # like a real bucket with none set); a dict is the four flags.
        self._configs = configs

    def list_buckets(self) -> dict:
        return {"Buckets": [{"Name": name} for name in self._buckets]}

    def get_public_access_block(self, Bucket: str) -> dict:  # noqa: N803 - matches boto3's signature
        config = self._configs.get(Bucket)
        if config is None:
            raise Exception("NoSuchPublicAccessBlockConfiguration")
        return {"PublicAccessBlockConfiguration": config}


class FakeIamClient:
    def __init__(self, users: list[str], with_mfa: set[str]) -> None:
        self._users = users
        self._with_mfa = with_mfa

    def list_users(self) -> dict:
        return {"Users": [{"UserName": name} for name in self._users]}

    def list_mfa_devices(self, UserName: str) -> dict:  # noqa: N803 - matches boto3's signature
        return {"MFADevices": [{"SerialNumber": "x"}] if UserName in self._with_mfa else []}


def test_find_s3_buckets_without_public_access_block_flags_unblocked_and_unconfigured() -> None:
    fully_blocked = {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }
    partially_blocked = {**fully_blocked, "RestrictPublicBuckets": False}
    client = FakeS3Client(
        buckets=["safe-bucket", "partial-bucket", "unconfigured-bucket"],
        configs={
            "safe-bucket": fully_blocked,
            "partial-bucket": partially_blocked,
            "unconfigured-bucket": None,
        },
    )
    exposed = find_s3_buckets_without_public_access_block(client)
    assert set(exposed) == {"partial-bucket", "unconfigured-bucket"}


def test_find_iam_users_without_mfa() -> None:
    client = FakeIamClient(users=["alice", "bob", "root"], with_mfa={"alice"})
    without_mfa = find_iam_users_without_mfa(client)
    assert set(without_mfa) == {"bob", "root"}


def test_is_aws_configured_false_by_default() -> None:
    assert is_aws_configured() is False


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Scan Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_cloud_scan_endpoint_reports_not_configured_without_aws_credentials(
    client: AsyncClient,
) -> None:
    await _signup(client, "scan1@example.com", "Scan Org 1")

    response = await client.post("/api/v1/security/cloud-scan")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["checks_run"] == []
    assert body["findings_created"] == 0


async def test_run_cloud_security_scan_creates_findings_when_configured(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr("app.secops.cloud_scanner.settings.aws_security_scan_access_key_id", "fake")
    monkeypatch.setattr(
        "app.secops.cloud_scanner.settings.aws_security_scan_secret_access_key", "fake-secret"
    )

    org_id = uuid.uuid4()

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            pass

        def client(self, service_name: str) -> object:
            if service_name == "s3":
                return FakeS3Client(buckets=["exposed-bucket"], configs={"exposed-bucket": None})
            if service_name == "iam":
                return FakeIamClient(users=["no-mfa-user"], with_mfa=set())
            raise ValueError(service_name)

    import app.secops.cloud_scanner as cloud_scanner_module

    monkeypatch.setattr(cloud_scanner_module, "boto3", type("_M", (), {"Session": FakeSession}))

    from app.core.models import Organization

    db_session.add(Organization(id=org_id, name="Fake Scan Org", slug=f"fake-{org_id}"))
    await db_session.flush()

    result = await run_cloud_security_scan(db_session, organization_id=org_id, actor_user_id=None)
    await db_session.commit()

    assert result.configured is True
    assert result.findings_created == 2

    findings = await db_session.execute(
        select(SecurityFinding).where(SecurityFinding.organization_id == org_id)
    )
    categories = sorted(f.category for f in findings.scalars().all())
    assert categories == ["cloud_misconfiguration", "identity"]
