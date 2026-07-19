from pathlib import Path

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    APP_NAME: str
    DATABASE_URL: str
    REDIS_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # Controls local API links used by Google and Microsoft OAuth callbacks.
    API_BASE_URL: str = "http://localhost:8000"
    GMAIL_CLIENT_ID: str | None = None
    GMAIL_CLIENT_SECRET: str | None = None
    GMAIL_REDIRECT_URI: str | None = None
    OUTLOOK_CLIENT_ID: str | None = None
    OUTLOOK_CLIENT_SECRET: str | None = None
    OUTLOOK_REDIRECT_URI: str | None = None

    # A Fernet key keeps external-provider credentials unreadable in the database.
    MAIL_TOKEN_ENCRYPTION_KEY: str | None = None

    # The worker is opt-in so development servers do not call email providers unexpectedly.
    MAIL_SYNC_ENABLED: bool = False
    MAIL_SYNC_INTERVAL_SECONDS: int = 300
    MAIL_SYNC_BATCH_SIZE: int = 50

    # A deployed OpenAI-compatible model can replace the local priority heuristic.
    LLM_PRIORITY_ENABLED: bool = False
    LLM_PRIORITY_API_URL: str | None = None
    LLM_PRIORITY_API_KEY: str | None = None
    LLM_PRIORITY_MODEL: str = "email-priority-classifier"
    SQL_ECHO: bool = False

    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"


settings = Settings()
