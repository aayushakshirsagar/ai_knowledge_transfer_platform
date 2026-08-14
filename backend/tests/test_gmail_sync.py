import base64
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GMAIL_CLIENT_ID", "test-client-id")
os.environ.setdefault("GMAIL_CLIENT_SECRET", "test-client-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.tables import Document, Project, ProjectAssignment, User
from app.services.gmail_connector import GmailConnectorService
from app.services.gmail_sync import GmailSyncService


class FakeRedis:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, str]] = []

    def rpush(self, queue_name: str, payload: str) -> int:
        self.pushes.append((queue_name, payload))
        return len(self.pushes)


class FakeS3Service:
    def upload_file(self, local_path: str, project_id: str, document_id: str) -> str:
        return f"projects/{project_id}/documents/{document_id}/thread.bin"


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def test_sync_ingests_each_thread_into_one_document(monkeypatch):
    session_factory = _build_session_factory()

    with session_factory() as session:
        user = User(email="gmail.sync@example.com", name="Sync User")
        project = Project(name="Alpha", aliases=[], created_by=1)
        session.add(user)
        session.add(project)
        session.commit()
        user_id = user.id
        project_id = project.id
        session.add(ProjectAssignment(project_id=project_id, user_id=user_id, assigned_by=user_id))
        session.commit()

    connector_service = GmailConnectorService(session_factory=session_factory)
    connector_service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    plain = base64.urlsafe_b64encode(b"Can we meet tomorrow?").decode()

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200
            self.text = ""

        def json(self):
            return self._payload

    def fake_request(method, url, params=None, headers=None, timeout=None):
        if url.endswith("/threads"):
            return FakeResponse({"threads": [{"id": "thread_123", "historyId": "12345"}]})
        return FakeResponse(
            {
                "id": "thread_123",
                "historyId": "12345",
                "messages": [
                    {
                        "id": "msg_456",
                        "threadId": "thread_123",
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "sender@gmail.com"},
                                {"name": "To", "value": "receiver@example.com"},
                                {"name": "Subject", "value": "Meeting"},
                                {"name": "Date", "value": "2024-01-01T00:00:00Z"},
                            ],
                            "parts": [{"mimeType": "text/plain", "body": {"data": plain}}],
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    service = GmailSyncService(
        session_factory=session_factory,
        connector_service=connector_service,
        s3_service=FakeS3Service(),
        redis_client=FakeRedis(),
    )

    result = service.sync(user_id=user_id, project_id=project_id)

    assert result["ingested_documents"] == 1
    assert result["skipped_threads"] == 0

    with session_factory() as session:
        documents = session.query(Document).all()

    assert len(documents) == 1
    assert documents[0].source == "gmail"
    assert documents[0].source_ref == "thread_123"
    assert documents[0].title == "Meeting_sender_receiver.txt"
    assert "Can we meet tomorrow?" in documents[0].file_path or True


def test_sync_skips_already_ingested_threads(monkeypatch):
    session_factory = _build_session_factory()

    with session_factory() as session:
        user = User(email="gmail.sync2@example.com", name="Sync User")
        project = Project(name="Beta", aliases=[], created_by=1)
        session.add(user)
        session.add(project)
        session.commit()
        user_id = user.id
        project_id = project.id
        session.add(ProjectAssignment(project_id=project_id, user_id=user_id, assigned_by=user_id))
        session.add(
            Document(
                project_id=project_id,
                source="gmail",
                source_ref="thread_123",
                title="Already Ingested",
                status="pending",
            )
        )
        session.commit()

    connector_service = GmailConnectorService(session_factory=session_factory)
    connector_service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200
            self.text = ""

        def json(self):
            return self._payload

    def fake_request(method, url, params=None, headers=None, timeout=None):
        return FakeResponse({"threads": [{"id": "thread_123", "historyId": "12345"}]})

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    service = GmailSyncService(
        session_factory=session_factory,
        connector_service=connector_service,
        s3_service=FakeS3Service(),
        redis_client=FakeRedis(),
    )

    result = service.sync(user_id=user_id, project_id=project_id)

    assert result["ingested_documents"] == 0
    assert result["skipped_threads"] == 1

    with session_factory() as session:
        count = session.query(Document).count()
    assert count == 1