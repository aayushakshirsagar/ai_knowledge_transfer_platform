import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/google-drive/callback")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.tables import Document, Project, ProjectAssignment, User
from app.services.google_drive_connector import GoogleDriveConnectorService
from app.services.google_drive_sync import GoogleDriveSyncService


class FakeRedis:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, str]] = []

    def rpush(self, queue_name: str, payload: str) -> int:
        self.pushes.append((queue_name, payload))
        return len(self.pushes)


class FakeS3Service:
    def upload_file(self, local_path: str, project_id: str, document_id: str) -> str:
        return f"projects/{project_id}/documents/{document_id}/drive-file.bin"


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def test_register_folder_and_create_documents(monkeypatch):
    session_factory = _build_session_factory()

    with session_factory() as session:
        user = User(email="sync.user@example.com", name="Sync User")
        project = Project(name="Alpha", aliases=[], created_by=1)
        session.add(user)
        session.add(project)
        session.commit()
        user_id = user.id
        project_id = project.id
        session.add(ProjectAssignment(project_id=project_id, user_id=user_id, assigned_by=user_id))
        session.commit()

    connector_service = GoogleDriveConnectorService(session_factory=session_factory)
    connector_service.store_refresh_token(user_id=user_id, refresh_token="refresh-token-123", scope="https://www.googleapis.com/auth/drive.readonly")

    service = GoogleDriveSyncService(session_factory=session_factory, s3_service=FakeS3Service(), redis_client=FakeRedis())
    config = service.register_folder(user_id=user_id, project_id=project_id, folder_id="folder-1", folder_name="Alpha Folder")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.content = b"file-bytes"

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get_access_token(refresh_token):
        return "token-123"

    def fake_requests_get(url, params, headers, timeout):
        return FakeResponse({
            "files": [
                {"id": "file-1", "name": "Doc One", "mimeType": "application/pdf", "parents": ["folder-1"], "createdTime": "2024-01-01T00:00:00Z", "modifiedTime": "2024-01-02T00:00:00Z", "webViewLink": "https://drive.google.com/file/d/file-1/view"},
            ]
        })

    monkeypatch.setattr(service, "_get_access_token", fake_get_access_token)
    import app.services.google_drive_sync as sync_module
    monkeypatch.setattr(sync_module.requests, "get", fake_requests_get)

    result = service.sync_folder(user_id=user_id, folder_config_id=config.id)

    with session_factory() as session:
        documents = session.query(Document).all()

    assert result["created_documents"] == 1
    assert documents[0].source_ref == "file-1"
    assert documents[0].title == "Doc One"
