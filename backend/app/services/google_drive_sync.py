from __future__ import annotations

from datetime import datetime
from typing import Any

import redis
import requests
from sqlalchemy import select

from app.core.settings import settings
from app.models.tables import Document, GoogleDriveFolderConfig, GoogleDriveSyncState, User
from app.services.google_drive_connector import GoogleDriveConnectorService
from app.services.ingestion_service import DocumentIngestionService
from app.storage.s3_storage import S3StorageService


class GoogleDriveSyncService:
    _EXPORT_MIME_TYPES: dict[str, str] = {
        "application/vnd.google-apps.document": "application/pdf",
        "application/vnd.google-apps.spreadsheet": "text/csv",
        "application/vnd.google-apps.presentation": "application/pdf",
        "application/vnd.google-apps.richText": "application/pdf",
        "application/vnd.google-apps.drawing": "application/pdf",
    }

    def __init__(self, session_factory=None, s3_service: S3StorageService | None = None, redis_client=None) -> None:
        self.session_factory = session_factory
        self.connector_service = GoogleDriveConnectorService(session_factory=session_factory)
        self.ingestion_service = DocumentIngestionService()
        self.s3_service = s3_service or S3StorageService()
        self.redis_client = redis_client or self._build_default_redis_client()

    def _build_default_redis_client(self) -> redis.Redis:
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for background queue support")
        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def register_folder(self, user_id: int, project_id: int, folder_id: str, folder_name: str | None = None) -> GoogleDriveFolderConfig:
        with self.session_factory() as session:
            existing = session.scalar(
                select(GoogleDriveFolderConfig).where(
                    GoogleDriveFolderConfig.user_id == user_id,
                    GoogleDriveFolderConfig.project_id == project_id,
                    GoogleDriveFolderConfig.folder_id == folder_id,
                )
            )
            if existing is not None:
                return existing

            config = GoogleDriveFolderConfig(
                user_id=user_id,
                project_id=project_id,
                folder_id=folder_id,
                folder_name=folder_name,
            )
            session.add(config)
            session.commit()
            session.refresh(config)
            return config

    def sync_folder(self, user_id: int, folder_config_id: int) -> dict[str, Any]:
        with self.session_factory() as session:
            folder_config = session.get(GoogleDriveFolderConfig, folder_config_id)
            if folder_config is None:
                raise ValueError("Folder configuration not found")

            current_user = session.get(User, folder_config.user_id)
            if current_user is None:
                raise RuntimeError("Google Drive folder owner user not found")

            token_data = self.connector_service.get_refresh_token_for_user(user_id)
            if not token_data or not token_data.get("refresh_token"):
                raise RuntimeError("Google Drive refresh token is not configured")

            state = session.scalar(
                select(GoogleDriveSyncState).where(
                    GoogleDriveSyncState.user_id == user_id,
                    GoogleDriveSyncState.folder_id == folder_config.folder_id,
                )
            )
            if state is None:
                state = GoogleDriveSyncState(user_id=user_id, folder_id=folder_config.folder_id)
                session.add(state)
                session.commit()
                session.refresh(state)

            access_token = self._get_access_token(token_data["refresh_token"])

            created_count = 0
            downloaded_count = 0
            for drive_file in self._list_folder_files(access_token, folder_config.folder_id):
                existing = session.scalar(
                    select(Document).where(
                        Document.project_id == folder_config.project_id,
                        Document.source == "drive",
                        Document.source_ref == drive_file["id"],
                    )
                )
                if existing is not None:
                    continue

                content = self._download_file(access_token, drive_file["id"], drive_file.get("mimeType", ""))
                if not content:
                    continue

                self.ingestion_service.upload_document_content(
                    content=content,
                    title=drive_file.get("name"),
                    filename=drive_file.get("name") or drive_file["id"],
                    source="drive",
                    source_ref=drive_file["id"],
                    project_id=folder_config.project_id,
                    db=session,
                    current_user=current_user,
                    s3_service=self.s3_service,
                    redis_client=self.redis_client,
                )
                created_count += 1
                downloaded_count += 1

            state.updated_at = datetime.utcnow()
            session.commit()

            return {
                "folder_id": folder_config.folder_id,
                "project_id": folder_config.project_id,
                "created_documents": created_count,
                "downloaded_files": downloaded_count,
            }

    def _list_folder_files(self, access_token: str, folder_id: str) -> Any:
        """Paged listing of all non-trashed files whose parent is the given folder."""
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "files(id,name,mimeType,parents,createdTime,modifiedTime,webViewLink)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        while True:
            response = requests.get(
                "https://www.googleapis.com/drive/v3/files",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            yield from payload.get("files", [])

            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            params["pageToken"] = page_token

    def _download_file(self, access_token: str, file_id: str, mime_type: str) -> bytes:
        """Download a file's bytes; Google-native types are exported to a portable format."""
        headers = {"Authorization": f"Bearer {access_token}"}
        export_mime_type = self._EXPORT_MIME_TYPES.get(mime_type)
        if export_mime_type is not None:
            url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
            params = {"mimeType": export_mime_type}
        elif mime_type.startswith("application/vnd.google-apps."):
            return b""
        else:
            url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
            params = {"alt": "media"}
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content

    def _get_access_token(self, refresh_token: str) -> str:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["access_token"]