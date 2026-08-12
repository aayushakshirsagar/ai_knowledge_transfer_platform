from __future__ import annotations

import redis
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.session import get_session
from app.models.tables import User
from app.storage.s3_storage import S3StorageService


def get_redis_client() -> redis.Redis:
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required for background queue support")
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_s3_service() -> S3StorageService:
    return S3StorageService()


def get_current_user(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_session),
) -> User:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )

    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-User-Id header value",
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
