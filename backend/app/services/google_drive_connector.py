from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import requests
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.tables import ConnectorCredential, ConnectorStatus, ConnectorType, OAuthToken


class GoogleDriveConnectorService:
    def __init__(self, session_factory=None):
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

    def exchange_authorization_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def store_refresh_token(self, user_id: int, refresh_token: str, scope: str) -> OAuthToken:
        with self.session_factory() as session:
            existing = session.scalar(
                select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.connector_type == ConnectorType.drive.value,
                )
            )

            if existing is None:
                token_row = OAuthToken(
                    user_id=user_id,
                    connector_type=ConnectorType.drive.value,
                    encrypted_access_token="",
                    encrypted_refresh_token=self._encrypt(refresh_token),
                    scope=scope,
                )
                session.add(token_row)
            else:
                existing.encrypted_refresh_token = self._encrypt(refresh_token)
                existing.scope = scope
                token_row = existing

            session.commit()
            session.refresh(token_row)
            return token_row

    def get_refresh_token_for_user(self, user_id: int) -> dict[str, Any] | None:
        with self.session_factory() as session:
            token_row = session.scalar(
                select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.connector_type == ConnectorType.drive.value,
                )
            )
            if token_row is None:
                return None
            return {
                "refresh_token": self._decrypt(token_row.encrypted_refresh_token) if token_row.encrypted_refresh_token else "",
                "scope": token_row.scope or "",
            }
