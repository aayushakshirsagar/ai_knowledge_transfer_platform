from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

import requests
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.tables import User
from app.services.google_drive_connector import GoogleDriveConnectorService
from app.services.google_drive_sync import GoogleDriveSyncService

router = APIRouter(prefix="/api/v1/google-drive", tags=["google-drive"])
service = GoogleDriveConnectorService()
sync_service = GoogleDriveSyncService(session_factory=SessionLocal)


@router.get("/connect")
def connect_google_drive(user_id: int) -> RedirectResponse:
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth credentials are not configured")

    auth_url = (
        "https://accounts.google.com/o/oauth2/auth"
        f"?client_id={settings.GOOGLE_OAUTH_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_OAUTH_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={settings.GOOGLE_OAUTH_SCOPES}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={user_id}"
    )
    print(auth_url)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
def google_drive_callback(code: str | None = None, state: str | None = None) -> dict[str, str]:
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    try:
        user_id = int(state)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        token_payload = service.exchange_authorization_code(
            code=code,
            redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to exchange authorization code: {exc}")

    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Google did not return a refresh token")

    scope = token_payload.get("scope") or settings.GOOGLE_OAUTH_SCOPES
    service.store_refresh_token(user_id=user_id, refresh_token=refresh_token, scope=scope)

    return {
        "message": "Google Drive connected successfully",
        "user_id": str(user_id),
    }


@router.post("/folders")
def register_folder(user_id: int, project_id: int, folder_id: str, folder_name: str | None = None) -> dict[str, object]:
    config = sync_service.register_folder(user_id=user_id, project_id=project_id, folder_id=folder_id, folder_name=folder_name)
    return {
        "id": config.id,
        "folder_id": config.folder_id,
        "project_id": config.project_id,
        "folder_name": config.folder_name,
    }


@router.post("/sync/{folder_config_id}")
def sync_folder(folder_config_id: int, user_id: int) -> dict[str, object]:
    result = sync_service.sync_folder(user_id=user_id, folder_config_id=folder_config_id)
    return result
