from __future__ import annotations

import base64
import time
from datetime import datetime
from typing import Any

import requests
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.tables import ConnectorType, OAuthToken


class GmailAPIError(Exception):
    """Raised for any Gmail API failure, carrying a user-friendly error contract."""

    def __init__(self, code: int, message: str, details: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def decode_base64_content(data: str) -> str:
    """Decode base64url Gmail message content into readable text."""
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


class GmailConnectorService:
    THREADS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory or SessionLocal
        self._fernet = self._build_fernet()

    def _build_fernet(self) -> Fernet:
        key_material = settings.JWT_SECRET.encode("utf-8")
        if len(key_material) < 32:
            key_material = key_material + b"=" * (32 - len(key_material))
        key = base64.urlsafe_b64encode(key_material[:32])
        return Fernet(key)

    def _encrypt(self, value: str) -> str:
        raw = value.encode("utf-8")
        return base64.urlsafe_b64encode(self._fernet.encrypt(raw)).decode("utf-8")

    def _decrypt(self, value: str) -> str:
        return self._fernet.decrypt(base64.urlsafe_b64decode(value.encode("utf-8"))).decode("utf-8")

    def store_tokens(self, user_id: int, access_token: str, refresh_token: str, scope: str) -> OAuthToken:
        with self.session_factory() as session:
            existing = session.scalar(
                select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.connector_type == ConnectorType.gmail.value,
                )
            )

            if existing is None:
                token_row = OAuthToken(
                    user_id=user_id,
                    connector_type=ConnectorType.gmail.value,
                    encrypted_access_token=self._encrypt(access_token),
                    encrypted_refresh_token=self._encrypt(refresh_token),
                    scope=scope,
                )
                session.add(token_row)
            else:
                existing.encrypted_access_token = self._encrypt(access_token)
                existing.encrypted_refresh_token = self._encrypt(refresh_token)
                existing.scope = scope
                token_row = existing

            session.commit()
            session.refresh(token_row)
            return token_row

    def get_tokens(self, user_id: int) -> dict[str, Any] | None:
        with self.session_factory() as session:
            token_row = session.scalar(
                select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.connector_type == ConnectorType.gmail.value,
                )
            )
            if token_row is None:
                return None
            return {
                "access_token": self._decrypt(token_row.encrypted_access_token) if token_row.encrypted_access_token else "",
                "refresh_token": self._decrypt(token_row.encrypted_refresh_token) if token_row.encrypted_refresh_token else "",
                "scope": token_row.scope or "",
            }

    def get_access_token(self, user_id: int) -> str:
        tokens = self.get_tokens(user_id)
        if not tokens or not tokens.get("access_token"):
            raise GmailAPIError(
                code=401,
                message="Gmail access token is not configured",
                details="Complete the Gmail OAuth flow for this user before calling the API",
            )
        return tokens["access_token"]

    def _refresh_and_store(self, user_id: int) -> None:
        tokens = self.get_tokens(user_id)
        if not tokens or not tokens.get("refresh_token"):
            raise GmailAPIError(
                code=401,
                message="Gmail refresh token is not configured",
                details="Re-run the Gmail OAuth flow for this user",
            )
        response = requests.post(
            self.TOKEN_URL,
            data={
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise GmailAPIError(
                code=401,
                message="Failed to refresh the Gmail access token",
                details=response.text[:200],
            )
        payload = response.json()
        new_access_token = payload.get("access_token")
        if not new_access_token:
            raise GmailAPIError(
                code=401,
                message="Gmail token refresh returned no access token",
                details=str(payload),
            )
        self.store_tokens(
            user_id=user_id,
            access_token=new_access_token,
            refresh_token=tokens["refresh_token"],
            scope=tokens.get("scope") or settings.GMAIL_SCOPES,
        )

    @staticmethod
    def _backoff_delay(response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return float(2 ** attempt)

    def _raise_api_error(self, response: requests.Response) -> None:
        code = response.status_code
        try:
            body = response.json()
            api_message = (body.get("error") or {}).get("message") or response.text[:200]
        except ValueError:
            api_message = response.text[:200]

        if code == 401:
            message = "Access token is invalid or expired"
        elif code == 403:
            message = "Insufficient Gmail permissions; the granted scope does not allow this operation"
        elif code == 404:
            message = "Thread or message not found"
        elif code == 429:
            message = "Too many requests; Gmail rate limit exceeded"
        else:
            message = "Gmail API request failed"
        raise GmailAPIError(code=code, message=message, details=api_message)

    def _request(self, method: str, url: str, user_id: int, params: dict[str, Any] | None = None, retries: int = 3) -> requests.Response:
        refreshed = False
        for attempt in range(retries + 1):
            headers = {"Authorization": f"Bearer {self.get_access_token(user_id)}"}
            response = requests.request(method, url, params=params, headers=headers, timeout=30)

            if response.status_code == 401 and not refreshed:
                self._refresh_and_store(user_id)
                refreshed = True
                continue

            if response.status_code == 429:
                time.sleep(self._backoff_delay(response, attempt))
                continue

            if response.status_code >= 400:
                self._raise_api_error(response)

            return response

        raise GmailAPIError(
            code=429,
            message="Gmail API request failed after retries",
            details="Rate limit or transient error persisted",
        )

    def list_threads(
        self,
        user_id: int,
        q: str = "",
        max_results: int = 20,
        label_ids: list[str] | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"maxResults": max_results}
        if q:
            params["q"] = q
        if label_ids:
            params["labelIds"] = ",".join(label_ids)
        if page_token:
            params["pageToken"] = page_token

        response = self._request("GET", self.THREADS_URL, user_id, params=params)
        payload = response.json()

        threads = payload.get("threads", [])
        result_size_estimate = payload.get("resultSizeEstimate", len(threads))
        return {
            "threads": threads,
            "nextPageToken": payload.get("nextPageToken"),
            "resultSizeEstimate": result_size_estimate,
            "total": result_size_estimate,
        }

    def get_thread(self, user_id: int, thread_id: str, format: str = "full") -> dict[str, Any]:
        url = f"{self.THREADS_URL}/{thread_id}"
        response = self._request("GET", url, user_id, params={"format": format})
        thread = response.json()

        for message in thread.get("messages", []):
            message["decodedContent"] = self._decode_message(message)
        return thread

    def _decode_message(self, message: dict[str, Any]) -> dict[str, str]:
        payload = message.get("payload") or {}
        text_parts: list[str] = []
        html_parts: list[str] = []
        self._collect_parts(payload, text_parts, html_parts)
        return {"text": "\n\n".join(text_parts), "html": "\n\n".join(html_parts)}

    def _collect_parts(self, payload: dict[str, Any], text_parts: list[str], html_parts: list[str]) -> None:
        mime_type = payload.get("mimeType", "")
        body = payload.get("body") or {}
        if body.get("data"):
            decoded = decode_base64_content(body["data"])
            if mime_type == "text/html":
                html_parts.append(decoded)
            elif mime_type == "text/plain" or mime_type.startswith("text/"):
                text_parts.append(decoded)
        for part in payload.get("parts") or []:
            self._collect_parts(part, text_parts, html_parts)
