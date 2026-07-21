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
    MAIL_SYNC_WORKER_LOCK_ID: int = 914159

    # A deployed OpenAI-compatible model can replace the local priority heuristic.
    LLM_PRIORITY_ENABLED: bool = False
    LLM_PRIORITY_BACKEND: str = "langchain"
    LLM_PRIORITY_API_URL: str | None = None
    LLM_PRIORITY_BASE_URL: str | None = None
    LLM_PRIORITY_API_KEY: str | None = None
    LLM_PRIORITY_MODEL: str = "email-priority-classifier"
    LLM_PRIORITY_TIMEOUT_SECONDS: float = 15
    LLM_PRIORITY_MAX_BODY_CHARACTERS: int = 2000
    LLM_PRIORITY_SEND_BODY_PREVIEW: bool = False
    LLM_PRIORITY_CLASSIFICATION_VERSION: str = "v1"

    # Meta WhatsApp Cloud API stays inactive until all of its credentials are supplied.
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_GRAPH_API_VERSION: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_ACCESS_TOKEN: str | None = None
    WHATSAPP_VERIFY_TOKEN: str | None = None
    WHATSAPP_APP_SECRET: str | None = None
    WHATSAPP_PRIORITY_TEMPLATE_NAME: str | None = None
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"
    WHATSAPP_MAX_DELIVERY_ATTEMPTS: int = 5
    SQL_ECHO: bool = False

    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"


settings = Settings()
