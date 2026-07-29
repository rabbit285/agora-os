from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import File
from app.core.schemas import FileOut, FileUploadRequest, FileUploadResponse
from app.core.storage import build_storage_key, presign_download, presign_upload
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload-url", response_model=FileUploadResponse)
async def create_upload_url(
    payload: FileUploadRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> FileUploadResponse:
    """Returns a short-lived signed PUT URL. The client uploads directly to
    object storage; the API never proxies file bytes (spec L3 Object
    Storage requirements)."""
    storage_key = build_storage_key(context.organization_id, payload.filename)
    file_record = File(
        organization_id=context.organization_id,
        storage_key=storage_key,
        original_filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        classification=payload.classification,
        uploaded_by=context.user.id,
    )
    db.add(file_record)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="core.file.upload_requested",
        object_type="file",
        object_id=str(file_record.id),
        after_state={"filename": payload.filename, "classification": payload.classification},
    )
    await db.commit()
    upload_url = presign_upload(storage_key, payload.content_type)
    return FileUploadResponse(file_id=file_record.id, upload_url=upload_url)


@router.get("/{file_id}", response_model=FileOut)
async def get_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> FileOut:
    file_record = await db.get(File, file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    out = FileOut.model_validate(file_record)
    out.download_url = presign_download(file_record.storage_key)
    return out
