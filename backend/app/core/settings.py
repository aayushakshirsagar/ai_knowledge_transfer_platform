from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Company Brain API"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # AI Models
    ANTHROPIC_API_KEY: str = ""
    OPEN_SOURCE_LLM_ENDPOINT: str = ""
    VOYAGE_API_KEY: str = ""

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # Qdrant
    QDRANT_URL: str
    QDRANT_API_KEY: str = ""

    # AWS
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = ""
    AWS_S3_BUCKET: str = ""

    # Slack
    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""

    # Microsoft Graph
    MS_GRAPH_CLIENT_ID: str = ""
    MS_GRAPH_CLIENT_SECRET: str = ""
    MS_TENANT_ID: str = ""

    # Google
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = ""
    GOOGLE_OAUTH_SCOPES: str = "https://www.googleapis.com/auth/drive.readonly"

    # Gmail
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = ""
    GMAIL_ACCESS_TOKEN_STORAGE: str = "database"
    GMAIL_SCOPES: str = "https://www.googleapis.com/auth/gmail.readonly"

    # WhatsApp
    WHATSAPP_BUSINESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    # Authentication
    JWT_SECRET: str

    model_config = SettingsConfigDict(
        env_file="../infra/.env",
        env_file_encoding="utf-8",
    )


settings = Settings()

## better way to access the environment variables
