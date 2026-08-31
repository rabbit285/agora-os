from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
    Storage requirements).

    Where the client supplies a content hash, the same bytes already held
    by this organization are answered here rather than uploaded again.
    Two states matter and they are different answers: a document already
    analysed is one the customer should be sent to, and one still
    processing is one they should be told to wait for — starting a second
    pipeline over it would produce a second set of evidence and gaps for
    one real-world policy.
    """
    if payload.content_hash:
        held = (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == context.organization_id,
                    File.content_hash == payload.content_hash,
                    File.processing_status.notin_(("failed", "duplicate")),
                )
                .order_by(File.created_at)
                .limit(1)
            )
        ).scalars().first()
        if held is not None:
            processing = held.processing_status in ("uploaded", "parsing", "analyzing")
            return FileUploadResponse(
                file_id=held.id,
                upload_url=None,
                status="processing" if processing else "duplicate",
                message=(
                    "This document is already being processed."
                    if processing
                    else "This document has already been uploaded."
                ),
            )

    storage_key = build_storage_key(context.organization_id, payload.filename)
    file_record = File(
        organization_id=context.organization_id,
        storage_key=storage_key,
        original_filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        classification=payload.classification,
        uploaded_by=context.user.id,
        # The client's claim. Verified against the real bytes by the
        # pipeline, which corrects it if it was wrong.
        content_hash=payload.content_hash,
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
    return FileUploadResponse(file_id=file_record.id, upload_url=upload_url, status="new")


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
