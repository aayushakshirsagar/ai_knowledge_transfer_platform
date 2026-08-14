from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_redis_client,
    get_s3_service,
    get_session,
)
from app.models.tables import User
from app.services.ingestion_service import DocumentIngestionService
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
    ingestion_service: DocumentIngestionService = Depends(DocumentIngestionService),
) -> DocumentUploadResponse:
    document = ingestion_service.upload_document(
        file=file,
        project_id=project_id,
        db=db,
        current_user=current_user,
        s3_service=s3_service,
        redis_client=redis_client,
    )

    return DocumentUploadResponse(document_id=document.id)