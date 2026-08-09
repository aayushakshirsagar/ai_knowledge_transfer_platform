import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GMAIL_CLIENT_ID", "test-client-id")
os.environ.setdefault("GMAIL_CLIENT_SECRET", "test-client-secret")

import pytest
from fastapi import HTTPException

import app.api.gmail as gmail_api
from app.services.gmail_connector import GmailAPIError


class FakeConnector:
    def __init__(self):
        self.called = {}

    def list_threads(self, user_id, q, max_results, label_ids, page_token):
        self.called = {
            "user_id": user_id,
            "q": q,
            "max_results": max_results,
            "label_ids": label_ids,
            "page_token": page_token,
        }
        return {
            "threads": [{"id": "thread_123", "historyId": "12345"}],
            "nextPageToken": "abc123",
            "resultSizeEstimate": 150,
            "total": 150,
        }

    def get_thread(self, user_id, thread_id, format):
        self.called = {"user_id": user_id, "thread_id": thread_id, "format": format}
        return {"id": thread_id, "historyId": "12345", "messages": []}


def test_list_threads_parses_query_params(monkeypatch):
    fake = FakeConnector()
    monkeypatch.setattr(gmail_api, "connector", fake)

    result = gmail_api.list_threads(
        user_id=2,
        q="is:unread",
        maxResults=100,
        labelIds="INBOX,UNREAD",
        pageToken="n1",
    )

    assert fake.called["user_id"] == 2
    assert fake.called["q"] == "is:unread"
    assert fake.called["max_results"] == 100
    assert fake.called["label_ids"] == ["INBOX", "UNREAD"]
    assert fake.called["page_token"] == "n1"
    assert result["total"] == 150
    assert result["nextPageToken"] == "abc123"


def test_list_threads_with_defaults(monkeypatch):
    fake = FakeConnector()
    monkeypatch.setattr(gmail_api, "connector", fake)

    result = gmail_api.list_threads(user_id=1, q="", maxResults=20, labelIds=None, pageToken=None)

    assert fake.called["label_ids"] is None
    assert fake.called["page_token"] is None
    assert result["threads"][0]["id"] == "thread_123"


def test_list_threads_maps_gmail_error_to_http_error(monkeypatch):
    class FailingConnector:
        def list_threads(self, user_id, q, max_results, label_ids, page_token):
            raise GmailAPIError(code=403, message="Insufficient Gmail permissions", details="Request had insufficient authentication scopes.")

    monkeypatch.setattr(gmail_api, "connector", FailingConnector())

    with pytest.raises(HTTPException) as exc_info:
        gmail_api.list_threads(user_id=1, q="", maxResults=20, labelIds=None, pageToken=None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"]["code"] == 403
    assert exc_info.value.detail["error"]["message"] == "Insufficient Gmail permissions"
    assert exc_info.value.detail["error"]["details"] == "Request had insufficient authentication scopes."


def test_get_thread_passes_format_and_returns_decoded(monkeypatch):
    fake = FakeConnector()
    monkeypatch.setattr(gmail_api, "connector", fake)

    result = gmail_api.get_thread(thread_id="thread_123", user_id=1, format="metadata")

    assert fake.called["thread_id"] == "thread_123"
    assert fake.called["format"] == "metadata"
    assert result["id"] == "thread_123"


def test_get_thread_maps_404_error(monkeypatch):
    class FailingConnector:
        def get_thread(self, user_id, thread_id, format):
            raise GmailAPIError(code=404, message="Thread or message not found", details="not found")

    monkeypatch.setattr(gmail_api, "connector", FailingConnector())

    with pytest.raises(HTTPException) as exc_info:
        gmail_api.get_thread(thread_id="missing", user_id=1, format="full")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"]["code"] == 404


def test_get_thread_rejects_empty_thread_id():
    with pytest.raises(HTTPException) as exc_info:
        gmail_api.get_thread(thread_id="   ", user_id=1, format="full")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"]["code"] == 400
