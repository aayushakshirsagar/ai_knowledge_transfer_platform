import base64
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GMAIL_CLIENT_ID", "test-client-id")
os.environ.setdefault("GMAIL_CLIENT_SECRET", "test-client-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.tables import OAuthToken, User
from app.services.gmail_connector import GmailAPIError, GmailConnectorService, decode_base64_content

def _build_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def _create_user(session_factory):
    with session_factory() as session:
        user = User(email="gmail.user@example.com", name="Gmail User")
        session.add(user)
        session.commit()
        return user.id


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._payload


def _make_service(session_factory):
    service = GmailConnectorService(session_factory=session_factory)
    return service


def test_store_and_load_tokens():
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)

    service.store_tokens(
        user_id=user_id,
        access_token="access-123",
        refresh_token="refresh-123",
        scope="https://www.googleapis.com/auth/gmail.readonly",
    )

    tokens = service.get_tokens(user_id)
    assert tokens["access_token"] == "access-123"
    assert tokens["refresh_token"] == "refresh-123"
    assert tokens["scope"] == "https://www.googleapis.com/auth/gmail.readonly"


def test_tokens_are_encrypted_at_rest():
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)

    service.store_tokens(user_id=user_id, access_token="secret-access", refresh_token="secret-refresh", scope="scope")

    with session_factory() as session:
        row = session.query(OAuthToken).first()
    assert row is not None
    assert "secret-access" not in row.encrypted_access_token
    assert "secret-refresh" not in row.encrypted_refresh_token


def test_store_tokens_is_upsert():
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)

    service.store_tokens(user_id=user_id, access_token="old", refresh_token="ref", scope="scope")
    service.store_tokens(user_id=user_id, access_token="new", refresh_token="ref", scope="scope")

    with session_factory() as session:
        count = session.query(OAuthToken).count()
    assert count == 1
    assert service.get_access_token(user_id) == "new"


def test_decode_base64_content():
    encoded = base64.urlsafe_b64encode(b"Hello, world!").decode()
    assert decode_base64_content(encoded) == "Hello, world!"
    assert decode_base64_content("") == ""
    assert decode_base64_content("not base64!!") == ""


def test_list_threads_builds_params_and_format(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    captured = {}

    def fake_request(method, url, params=None, headers=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return FakeResponse(
            status_code=200,
            payload={
                "threads": [{"id": "thread_123", "historyId": "12345"}],
                "nextPageToken": "abc123",
                "resultSizeEstimate": 150,
            },
        )

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    result = service.list_threads(
        user_id=user_id,
        q="from:john@gmail.com",
        max_results=50,
        label_ids=["INBOX", "UNREAD"],
        page_token="abc123",
    )

    assert captured["method"] == "GET"
    assert captured["url"] == "https://gmail.googleapis.com/gmail/v1/users/me/threads"
    assert captured["headers"]["Authorization"] == "Bearer tok-1"
    assert captured["params"]["maxResults"] == 50
    assert captured["params"]["q"] == "from:john@gmail.com"
    assert captured["params"]["labelIds"] == "INBOX,UNREAD"
    assert captured["params"]["pageToken"] == "abc123"
    assert result["threads"][0]["id"] == "thread_123"
    assert result["nextPageToken"] == "abc123"
    assert result["resultSizeEstimate"] == 150
    assert result["total"] == 150


def test_get_thread_decodes_body_and_parts(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    plain = base64.urlsafe_b64encode(b"Hey, can we meet tomorrow?").decode()
    html = base64.urlsafe_b64encode(b"<p>Hey, can we meet tomorrow?</p>").decode()

    def fake_request(method, url, params=None, headers=None, timeout=None):
        return FakeResponse(
            status_code=200,
            payload={
                "id": "thread_123",
                "historyId": "12345",
                "messages": [
                    {
                        "id": "msg_456",
                        "threadId": "thread_123",
                        "labelIds": ["INBOX", "UNREAD"],
                        "snippet": "Hey, can we meet tomorrow?",
                        "payload": {
                            "mimeType": "multipart/alternative",
                            "headers": [
                                {"name": "From", "value": "sender@gmail.com"},
                                {"name": "Subject", "value": "Meeting Tomorrow"},
                            ],
                            "body": {},
                            "parts": [
                                {"mimeType": "text/plain", "body": {"data": plain}},
                                {"mimeType": "text/html", "body": {"data": html}},
                            ],
                        },
                        "sizeEstimate": 12345,
                        "historyId": "12345",
                    }
                ],
            },
        )

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    result = service.get_thread(user_id=user_id, thread_id="thread_123", format="full")

    message = result["messages"][0]
    assert result["id"] == "thread_123"
    assert message["id"] == "msg_456"
    assert message["decodedContent"]["text"] == "Hey, can we meet tomorrow?"
    assert message["decodedContent"]["html"] == "<p>Hey, can we meet tomorrow?</p>"


def test_401_triggers_token_refresh_and_retry(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="expired", refresh_token="ref", scope="scope")

    calls = []

    def fake_request(method, url, params=None, headers=None, timeout=None):
        calls.append(headers["Authorization"])
        if len(calls) == 1:
            return FakeResponse(status_code=401)
        return FakeResponse(status_code=200, payload={"threads": [], "resultSizeEstimate": 0})

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    def fake_refresh(user_id):
        service.store_tokens(user_id=user_id, access_token="fresh-token", refresh_token="ref", scope="scope")

    monkeypatch.setattr(service, "_refresh_and_store", fake_refresh)

    result = service.list_threads(user_id=user_id)

    assert len(calls) == 2
    assert calls[0] == "Bearer expired"
    assert calls[1] == "Bearer fresh-token"
    assert result["total"] == 0


def test_refresh_flow_exchanges_refresh_token(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="old", refresh_token="refresh-me", scope="scope")

    def fake_post(url, data, timeout):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "refresh-me"
        return FakeResponse(status_code=200, payload={"access_token": "brand-new"})

    monkeypatch.setattr("app.services.gmail_connector.requests.post", fake_post)

    service._refresh_and_store(user_id)

    tokens = service.get_tokens(user_id)
    assert tokens["access_token"] == "brand-new"
    assert tokens["refresh_token"] == "refresh-me"


def test_429_uses_exponential_backoff_and_retries(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    sleeps = []
    statuses = [429, 429, 200]

    def fake_request(method, url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=statuses.pop(0), payload={"threads": [], "resultSizeEstimate": 0})

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)
    monkeypatch.setattr("app.services.gmail_connector.time.sleep", sleeps.append)

    result = service.list_threads(user_id=user_id)

    assert sleeps == [1.0, 2.0]
    assert result["total"] == 0


def test_403_raises_insufficient_scope(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    def fake_request(method, url, params=None, headers=None, timeout=None):
        response = FakeResponse(status_code=403, payload={"error": {"message": "Request had insufficient authentication scopes."}})
        response.text = '{"error": {"message": "Request had insufficient authentication scopes."}}'
        return response

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    try:
        service.list_threads(user_id=user_id)
        assert False, "expected GmailAPIError"
    except GmailAPIError as exc:
        assert exc.code == 403
        assert "scope" in exc.message.lower()


def test_404_raises_thread_not_found(monkeypatch):
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)
    service.store_tokens(user_id=user_id, access_token="tok-1", refresh_token="ref", scope="scope")

    def fake_request(method, url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=404, payload={"error": {"message": "Not Found"}})

    monkeypatch.setattr("app.services.gmail_connector.requests.request", fake_request)

    try:
        service.get_thread(user_id=user_id, thread_id="missing", format="full")
        assert False, "expected GmailAPIError"
    except GmailAPIError as exc:
        assert exc.code == 404
        assert "not found" in exc.message.lower()


def test_no_tokens_raises_401():
    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)
    service = _make_service(session_factory)

    try:
        service.list_threads(user_id=user_id)
        assert False, "expected GmailAPIError"
    except GmailAPIError as exc:
        assert exc.code == 401


def test_gmail_and_drive_tokens_share_one_table_but_stay_isolated():
    from app.services.google_drive_connector import GoogleDriveConnectorService

    session_factory = _build_session_factory()
    user_id = _create_user(session_factory)

    gmail_service = _make_service(session_factory)
    gmail_service.store_tokens(
        user_id=user_id,
        access_token="gmail-access",
        refresh_token="gmail-refresh",
        scope="https://www.googleapis.com/auth/gmail.readonly",
    )

    drive_service = GoogleDriveConnectorService(session_factory=session_factory)
    drive_service.store_refresh_token(
        user_id=user_id,
        refresh_token="drive-refresh",
        scope="https://www.googleapis.com/auth/drive.readonly",
    )

    assert gmail_service.get_tokens(user_id)["access_token"] == "gmail-access"
    assert gmail_service.get_tokens(user_id)["refresh_token"] == "gmail-refresh"
    assert gmail_service.get_tokens(user_id)["scope"] == "https://www.googleapis.com/auth/gmail.readonly"
    assert drive_service.get_refresh_token_for_user(user_id)["refresh_token"] == "drive-refresh"

    with session_factory() as session:
        rows = session.query(OAuthToken).order_by(OAuthToken.connector_type).all()
    assert [row.connector_type for row in rows] == ["drive", "gmail"]

    gmail_service.store_tokens(
        user_id=user_id,
        access_token="gmail-access-2",
        refresh_token="gmail-refresh-2",
        scope="https://www.googleapis.com/auth/gmail.readonly",
    )
    with session_factory() as session:
        count = session.query(OAuthToken).count()
    assert count == 2
    assert gmail_service.get_tokens(user_id)["access_token"] == "gmail-access-2"
    assert drive_service.get_refresh_token_for_user(user_id)["refresh_token"] == "drive-refresh"
