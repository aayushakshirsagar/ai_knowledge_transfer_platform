from __future__ import annotations

import os
from typing import Any

import boto3

try:
    from app.core.settings import settings
except Exception:  # pragma: no cover - fallback for tests without env vars
    settings = None


class S3StorageService:
    """Simple S3-backed document storage service for ingestion workflows."""

    def __init__(self, bucket_name: str | None = None, client: Any | None = None) -> None:
        self.bucket_name = bucket_name or self._resolve_bucket_name()
        self.client = client or self._build_default_client()

    def _resolve_bucket_name(self) -> str:
        if settings is None:
            raise RuntimeError("A bucket name or AWS S3 bucket configuration must be provided")
        return settings.AWS_S3_BUCKET

    def _build_default_client(self) -> Any:
        return boto3.client("s3")

    def _build_key(self, project_id: str, document_id: str, filename: str | None = None) -> str:
        base_key = f"projects/{project_id}/documents/{document_id}"
        if filename:
            return f"{base_key}/{filename}"
        return base_key

    def upload_file(self, local_path: str, project_id: str, document_id: str) -> str:
        filename = os.path.basename(local_path)
        key = self._build_key(project_id=project_id, document_id=document_id, filename=filename)
        with open(local_path, "rb") as handle:
            self.client.put_object(Bucket=self.bucket_name, Key=key, Body=handle)
        return key

    def get_signed_url(self, key: str, expiry_seconds: int = 3600) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expiry_seconds,
        )
