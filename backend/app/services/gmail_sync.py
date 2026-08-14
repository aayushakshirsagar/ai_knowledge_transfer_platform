from __future__ import annotations

import re
from typing import Any

import redis
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.tables import Document, User
from app.services.gmail_connector import GmailConnectorService
from app.services.ingestion_service import DocumentIngestionService
from app.storage.s3_storage import S3StorageService


class GmailSyncService:
    def __init__(
        self,
        session_factory=None,
        connector_service: GmailConnectorService | None = None,
        s3_service: S3StorageService | None = None,
        redis_client=None,
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.connector_service = connector_service or GmailConnectorService(session_factory=session_factory)
        self.ingestion_service = DocumentIngestionService()
        self.s3_service = s3_service
        self.redis_client = redis_client

    def _get_s3_service(self) -> S3StorageService:
        if self.s3_service is None:
            self.s3_service = S3StorageService()
        return self.s3_service

    def _get_redis_client(self) -> redis.Redis:
        if self.redis_client is None:
            if not settings.REDIS_URL:
                raise RuntimeError("REDIS_URL is required for background queue support")
            self.redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.redis_client

    def sync(self, user_id: int, project_id: int) -> dict[str, Any]:
        with self.session_factory() as session:
            current_user = session.get(User, user_id)
            if current_user is None:
                raise ValueError("User not found")

            thread_page = self.connector_service.list_threads(user_id=user_id)
            threads = thread_page.get("threads", [])

            s3_service = self._get_s3_service()
            redis_client = self._get_redis_client()

            ingested = 0
            skipped = 0
            for summary in threads:
                thread_id = summary["id"]
                existing = session.scalar(
                    select(Document).where(
                        Document.project_id == project_id,
                        Document.source == "gmail",
                        Document.source_ref == thread_id,
                    )
                )
                if existing is not None:
                    skipped += 1
                    continue

                thread = self.connector_service.get_thread(user_id=user_id, thread_id=thread_id)
                content, filename = self._build_document(thread)

                self.ingestion_service.upload_document_content(
                    content=content.encode("utf-8"),
                    title=filename,
                    filename=filename,
                    source="gmail",
                    source_ref=thread_id,
                    project_id=project_id,
                    db=session,
                    current_user=current_user,
                    s3_service=s3_service,
                    redis_client=redis_client,
                )
                ingested += 1

            session.commit()

            return {
                "user_id": user_id,
                "project_id": project_id,
                "ingested_documents": ingested,
                "skipped_threads": skipped,
            }

    def _build_document(self, thread: dict[str, Any]) -> tuple[str, str]:
        messages = thread.get("messages", [])
        blocks: list[str] = []
        for message in messages:
            headers = self._headers(message)
            body = (message.get("decodedContent") or {}).get("text", "").strip()
            block = (
                f"From: {headers.get('From', '')}\n"
                f"To: {headers.get('To', '')}\n"
                f"Date: {headers.get('Date', '')}\n"
                f"Subject: {headers.get('Subject', '')}\n\n"
                f"{body}"
            ).strip()
            blocks.append(block)
        content = "\n\n".join(blocks)
        filename = self._build_filename(messages)
        return content, filename

    def _build_filename(self, messages: list[dict[str, Any]]) -> str:
        first = messages[0] if messages else {}
        headers = self._headers(first)
        subject = headers.get("Subject") or "no-subject"
        sender = self._local_part(headers.get("From")) or "unknown"
        receiver = self._local_part(headers.get("To"))
        name = f"{subject}_{sender}" if receiver is None else f"{subject}_{sender}_{receiver}"
        return self._sanitize_filename(name) + ".txt"

    def _headers(self, message: dict[str, Any]) -> dict[str, str]:
        payload = message.get("payload") or {}
        return {header.get("name", ""): header.get("value", "") for header in payload.get("headers") or []}

    @staticmethod
    def _local_part(value: str | None) -> str | None:
        if not value:
            return None
        match = re.search(r"[\w.+-]+@[\w.-]+", value)
        if match is None:
            return None
        return match.group(0).split("@")[0]

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        return re.sub(r'[\\/:*?"<>|]+', "_", value)