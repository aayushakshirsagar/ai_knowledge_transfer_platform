"""Unified OAuth token storage for Google connectors (Gmail, Drive, etc.)."""

from alembic import op
import sqlalchemy as sa

revision = "0003_gmail_oauth"
down_revision = "0002_google_drive_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_type", sa.String(length=32), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "connector_type", name="uq_oauth_tokens_user_connector"),
    )

    # Carry over any Drive tokens created by 0002 (refresh token only; access token was never persisted).
    op.execute(
        """
        INSERT INTO oauth_tokens
            (user_id, connector_type, encrypted_access_token, encrypted_refresh_token, scope, created_at, updated_at)
        SELECT user_id, 'drive', '', encrypted_refresh_token, scope, created_at, updated_at
        FROM google_drive_oauth_tokens
        """
    )

    op.drop_table("google_drive_oauth_tokens")


def downgrade() -> None:
    op.create_table(
        "google_drive_oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.execute(
        """
        INSERT INTO google_drive_oauth_tokens
            (user_id, encrypted_refresh_token, scope, created_at, updated_at)
        SELECT user_id, encrypted_refresh_token, scope, created_at, updated_at
        FROM oauth_tokens
        WHERE connector_type = 'drive'
        """
    )

    op.drop_table("oauth_tokens")
