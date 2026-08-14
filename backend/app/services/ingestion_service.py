from __future__ import annotations

import os
import shutil
import tempfile
from typing import Callable

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.ingestion.queue import enqueue_document_parse
from app.models.tables import (
    Document,
    DocumentSource,
    DocumentStatus,
    ProjectAssignment,
    User,
)
from app.storage.s3_storage import S3StorageService


class DocumentIngestionService:
    def upload_document(
        self,
        file: UploadFile,
        project_id: int,
        db: Session,
        current_user: User,
        s3_service: S3StorageService,
        redis_client,
        source: str = DocumentSource.manual_upload.value,
        source_ref: str | None = None,
    ) -> Document:
        return self._ingest(
            project_id=project_id,
            db=db,
            current_user=current_user,
            s3_service=s3_service,
            redis_client=redis_client,
            title=file.filename,
            source=source,
            source_ref=source_ref,
            filename=os.path.basename(file.filename),
            write_func=lambda handle: shutil.copyfileobj(file.file, handle),
        )

    def upload_document_content(
        self,
        *,
        content: bytes,
        title: str | None,
        filename: str | None,
        source: str,
        source_ref: str | None,
        project_id: int,
        db: Session,
        current_user: User,
        s3_service: S3StorageService,
        redis_client,
    ) -> Document:
        return self._ingest(
            project_id=project_id,
            db=db,
            current_user=current_user,
            s3_service=s3_service,
            redis_client=redis_client,
            title=title,
            source=source,
            source_ref=source_ref,
            filename=filename,
            write_func=lambda handle: handle.write(content),
        )

    def _ingest(
        self,
        *,
        project_id: int,
        db: Session,
        current_user: User,
        s3_service: S3StorageService,
        redis_client,
        title: str | None,
        source: str,
        source_ref: str | None,
        filename: str | None,
        write_func: Callable[[object], None],
    ) -> Document:
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
            source=source,
            source_ref=source_ref,
            status=DocumentStatus.pending.value,
            uploaded_by=current_user.id,
            title=title,
        )

        db.add(document)
        db.flush()

        temp_dir = tempfile.mkdtemp()
        try:
            filename = filename or f"upload-{document.id}"
            local_path = os.path.join(temp_dir, filename)

            with open(local_path, "wb") as handle:
                write_func(handle)

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

        return document