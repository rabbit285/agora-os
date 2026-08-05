"""CSV import for the Sales Lead Finder (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §13). Reuses the existing
presigned-upload flow (app.routers.files) for the file itself and
app.sales.save_service for the actual dedupe-aware create.

Every imported row becomes a NormalizedCompany/NormalizedPerson with
provider="csv" — save_service maps that to
verification_status="user_entered" (never "provider_supplied"), so an
imported row can never be mistaken for a provider-verified one. Column
mapping is only ever a suggestion the caller must confirm/override before
`import_rows` is called; nothing here auto-commits a mapping.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.sales import save_service
from app.sales.providers.schemas import NormalizedCompany, NormalizedPerson

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# target field -> required
COMPANY_TARGET_FIELDS: dict[str, bool] = {
    "name": True,
    "domain": False,
    "website": False,
    "industry": False,
    "employee_count": False,
    "location": False,
}

PERSON_TARGET_FIELDS: dict[str, bool] = {
    "full_name": True,
    "email": False,
    "title": False,
    "company_domain": False,
    "location": False,
    "phone": False,
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("company", "company name", "organization", "account"),
    "domain": ("website domain", "company domain"),
    "website": ("url", "company url", "site", "web site"),
    "industry": ("sector", "vertical"),
    "employee_count": ("employees", "headcount", "size", "# employees"),
    "location": ("city", "hq", "headquarters", "address"),
    "full_name": ("name", "contact name", "person", "full name"),
    "email": ("email address", "work email", "e-mail"),
    "title": ("job title", "position", "role"),
    "company_domain": ("company", "domain", "employer domain", "company website"),
    "phone": ("phone number", "mobile", "telephone"),
}


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def suggest_column_mapping(headers: list[str], record_type: str) -> dict[str, str | None]:
    """Case-insensitive heuristic match of CSV headers to target fields —
    always returned to the caller for review, never applied automatically."""
    target_fields = COMPANY_TARGET_FIELDS if record_type == "company" else PERSON_TARGET_FIELDS
    normalized_headers = {_normalize_header(h): h for h in headers}
    mapping: dict[str, str | None] = {}
    for target in target_fields:
        candidates = [target.replace("_", " "), target, *_ALIASES.get(target, ())]
        matched = None
        for candidate in candidates:
            normalized_candidate = _normalize_header(candidate)
            if normalized_candidate in normalized_headers:
                matched = normalized_headers[normalized_candidate]
                break
        mapping[target] = matched
    return mapping


def _decode(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8-sig", errors="replace")


def _read_reader(file_bytes: bytes) -> csv.DictReader[str]:
    return csv.DictReader(io.StringIO(_decode(file_bytes)))


def read_all_rows(file_bytes: bytes) -> list[dict[str, str]]:
    reader = _read_reader(file_bytes)
    return [{k: (v or "") for k, v in row.items() if k is not None} for row in reader]


@dataclass
class CsvPreview:
    headers: list[str]
    sample_rows: list[dict[str, str]]
    suggested_mapping: dict[str, str | None]
    total_rows: int


def parse_preview(file_bytes: bytes, *, record_type: str, sample_size: int = 20) -> CsvPreview:
    reader = _read_reader(file_bytes)
    rows = [{k: (v or "") for k, v in row.items() if k is not None} for row in reader]
    headers = list(reader.fieldnames or [])
    return CsvPreview(
        headers=headers,
        sample_rows=rows[:sample_size],
        suggested_mapping=suggest_column_mapping(headers, record_type),
        total_rows=len(rows),
    )


def _mapped_value(
    row: dict[str, str], column_mapping: dict[str, str | None], field_name: str
) -> str | None:
    header = column_mapping.get(field_name)
    if not header:
        return None
    value = row.get(header)
    value = value.strip() if value else None
    return value or None


@dataclass
class ImportResult:
    total_rows: int
    imported_rows: int
    skipped_rows: int
    error_rows: list[dict[str, Any]]


def _domain_from_website(website: str) -> str:
    return (
        website.replace("https://", "").replace("http://", "").split("/")[0].removeprefix("www.").lower()
    )


def _build_company(row: dict[str, str], column_mapping: dict[str, str | None]) -> NormalizedCompany:
    name = _mapped_value(row, column_mapping, "name")
    if not name:
        raise ValueError("Missing required field: name")
    employee_count_raw = _mapped_value(row, column_mapping, "employee_count")
    employee_count = (
        int(employee_count_raw)
        if employee_count_raw and employee_count_raw.replace(",", "").isdigit()
        else None
    )
    location = _mapped_value(row, column_mapping, "location")
    domain = _mapped_value(row, column_mapping, "domain")
    website = _mapped_value(row, column_mapping, "website")
    if not domain and website:
        # Dedupe (save_service.save_company_as_account) matches on
        # `domain` — a CSV that only has a "website" column must still
        # participate in that match, not silently skip it.
        domain = _domain_from_website(website)
    return NormalizedCompany(
        provider="csv",
        provider_record_id=f"csv-{uuid.uuid4()}",
        name=name,
        domain=domain,
        website=website,
        industry=_mapped_value(row, column_mapping, "industry"),
        locations=[location] if location else [],
        employee_count=employee_count,
        employee_range=None,
        revenue_range=None,
        funding_stage=None,
        total_funding_usd=None,
        technologies=[],
        linkedin_url=None,
        source_url=None,
        retrieved_at=datetime.now(UTC),
        raw=dict(row),
    )


def _build_person(row: dict[str, str], column_mapping: dict[str, str | None]) -> NormalizedPerson:
    full_name = _mapped_value(row, column_mapping, "full_name")
    if not full_name:
        raise ValueError("Missing required field: full_name")
    email = _mapped_value(row, column_mapping, "email")
    if email and not _EMAIL_RE.match(email):
        raise ValueError(f"Invalid email format: {email}")
    phone = _mapped_value(row, column_mapping, "phone")
    return NormalizedPerson(
        provider="csv",
        provider_record_id=f"csv-{uuid.uuid4()}",
        full_name=full_name,
        title=_mapped_value(row, column_mapping, "title"),
        seniority=None,
        department=None,
        current_company_name=None,
        current_company_domain=_mapped_value(row, column_mapping, "company_domain"),
        location=_mapped_value(row, column_mapping, "location"),
        email=email.lower() if email else None,
        email_status="unverified" if email else "unavailable",
        phone=phone,
        phone_status="unverified" if phone else "unavailable",
        linkedin_url=None,
        source_url=None,
        retrieved_at=datetime.now(UTC),
        raw=dict(row),
    )


async def import_rows(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    record_type: str,
    rows: list[dict[str, str]],
    column_mapping: dict[str, str | None],
    ip_address: str | None,
    user_agent: str | None,
) -> ImportResult:
    imported = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        try:
            if record_type == "company":
                company = _build_company(row, column_mapping)
                await save_service.save_company_as_account(
                    db,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    company=company,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            else:
                person = _build_person(row, column_mapping)
                await save_service.save_person_as_contact(
                    db,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    person=person,
                    account_id=None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            imported += 1
        except Exception as exc:  # noqa: BLE001 - recorded per-row, loop continues
            skipped += 1
            errors.append({"row_number": index, "error": str(exc)})

    return ImportResult(
        total_rows=len(rows), imported_rows=imported, skipped_rows=skipped, error_rows=errors
    )
