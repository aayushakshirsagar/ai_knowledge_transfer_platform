from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ingestion import router as ingestion_router
from app.api.dependencies import get_current_user, get_redis_client, get_s3_service, get_session
from app.models.tables import ProjectAssignment, User


class FakeRedis:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, str]] = []

    def rpush(self, queue_name: str, payload: str) -> int:
        self.pushes.append((queue_name, payload))
        return len(self.pushes)


class FakeS3Service:
    def upload_file(self, local_path: str, project_id: str, document_id: str) -> str:
        if not os.path.exists(local_path):
            raise AssertionError("File not found before upload")
        return f"projects/{project_id}/documents/{document_id}/{os.path.basename(local_path)}"


class FakeSession:
    def __init__(self, assignment: object) -> None:
        self.assignment = assignment
        self.document = None
        self.committed = False
        self.rolled_back = False

    def query(self, model: type) -> "FakeSession":
        return self

    def filter(self, *args, **kwargs) -> "FakeSession":
        return self

    def first(self) -> object:
        return self.assignment

    def add(self, obj: object) -> None:
        self.document = obj

    def flush(self) -> None:
        if self.document is not None:
            setattr(self.document, "id", 1)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_upload_document_saves_and_enqueues() -> None:
    app = FastAPI()
    app.include_router(ingestion_router)

    fake_user = User(id=42, email="test@example.com", name="Test User", role="employee")
    fake_session = FakeSession(ProjectAssignment(project_id=123, user_id=42, assigned_by=1))
    fake_redis = FakeRedis()
    fake_s3 = FakeS3Service()

    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_s3_service] = lambda: fake_s3

    client = TestClient(app)
    response = client.post(
        "/ingestion/upload",
        data={"project_id": "123"},
        files={"file": ("hello.txt", b"hello world", "text/plain")},
        headers={"X-User-Id": "42"},
    )

    assert response.status_code == 200
    assert response.json() == {"document_id": 1}
    assert fake_redis.pushes
    queue_name, payload = fake_redis.pushes[0]
    assert queue_name == "document_parse_queue"
    assert "document_id" in payload and "project_id" in payload
