from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

# spec §65's 14 named report types.
REPORT_TYPES: dict[str, str] = {
    "executive_business_ai": "Executive Business AI Report",
    "compliance": "Compliance Report",
    "security_posture": "Security Posture Report",
    "gdpr": "GDPR Report",
    "eu_ai_act": "EU AI Act Report",
    "ai_inventory": "AI Inventory",
    "risk": "Risk Report",
    "vendor": "Vendor Report",
    "sales_performance": "Sales Performance",
    "pipeline": "Pipeline Report",
    "support_performance": "Support Performance",
    "automation_roi": "Automation ROI",
    "audit_evidence_pack": "Audit Evidence Pack",
    "board": "Board Report",
}

# spec §65's export list is PDF/DOCX/XLSX/CSV/Secure link; "Secure link"
# is the download-delivery mechanism every format already uses (see
# app.reporting.models.Report), not a 5th file format to render.
REPORT_FORMATS: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


class ReportTypeOut(BaseModel):
    key: str
    label: str


class ReportCreate(BaseModel):
    report_type: str
    format: str

    @field_validator("report_type")
    @classmethod
    def _validate_report_type(cls, value: str) -> str:
        if value not in REPORT_TYPES:
            raise ValueError(f"Unknown report_type: {value}")
        return value

    @field_validator("format")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        if value not in REPORT_FORMATS:
            raise ValueError(f"Unknown format: {value}")
        return value


class ReportOut(BaseModel):
    id: uuid.UUID
    report_type: str
    format: str
    status: str
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportDownloadOut(BaseModel):
    download_url: str
