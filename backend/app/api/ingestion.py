from __future__ import annotations

import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_redis_client,
    get_s3_service,
    get_session,
)
from app.ingestion.queue import enqueue_document_parse
from app.models.tables import (
    Document,
    DocumentSource,
    DocumentStatus,
    ProjectAssignment,
    User,
)
from app.storage.s3_storage import S3StorageService


class DocumentUploadResponse(BaseModel):
    document_id: int


router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    s3_service: S3StorageService = Depends(get_s3_service),
    redis_client=Depends(get_redis_client),
) -> DocumentUploadResponse:
    assignment = (
        db.query(ProjectAssignment)
        .filter(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.user_id == current_user.id,
        )
        .first()
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this project",
        )

    document = Document(
        project_id=project_id,
        source=DocumentSource.manual_upload.value,
        status=DocumentStatus.pending.value,
        uploaded_by=current_user.id,
        title=file.filename,
    )

    db.add(document)
    db.flush()

    temp_dir = tempfile.mkdtemp()
    try:
        filename = os.path.basename(file.filename) or f"upload-{document.id}"
        local_path = os.path.join(temp_dir, filename)

        with open(local_path, "wb") as handle:
            shutil.copyfileobj(file.file, handle)

        s3_key = s3_service.upload_file(
            local_path=local_path,
            project_id=str(project_id),
            document_id=str(document.id),
        )
        document.file_path = s3_key
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document and schedule parsing",
        ) from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    enqueue_document_parse(
        redis_client=redis_client,
        document_id=document.id,
        project_id=project_id,
    )

    return DocumentUploadResponse(document_id=document.id)
