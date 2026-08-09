import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/google-drive/callback")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.tables import User
from app.services.google_drive_connector import GoogleDriveConnectorService


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def test_encrypt_and_decrypt_round_trip():
    service = GoogleDriveConnectorService(session_factory=_build_session_factory())

    token = "refresh-token-123"
    encrypted = service._encrypt(token)

    assert encrypted != token
    assert service._decrypt(encrypted) == token


def test_store_and_load_refresh_token():
    session_factory = _build_session_factory()
    with session_factory() as session:
        user = User(email="drive.user@example.com", name="Drive User")
        session.add(user)
        session.commit()
        user_id = user.id

    service = GoogleDriveConnectorService(session_factory=session_factory)
    service.store_refresh_token(user_id=user_id, refresh_token="refresh-token-456", scope="https://www.googleapis.com/auth/drive.readonly")

    stored = service.get_refresh_token_for_user(user_id=user_id)

    assert stored is not None
    assert stored["refresh_token"] == "refresh-token-456"
    assert stored["scope"] == "https://www.googleapis.com/auth/drive.readonly"
