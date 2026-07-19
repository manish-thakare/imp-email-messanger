from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context=CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def hash_password(password: str) -> str:
    """Create a one-way password hash for a newly registered user."""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Check a supplied password against its stored password hash."""
    return pwd_context.verify(password,hashed)


def create_access_token(data: dict[str, Any]) -> str:
    """Sign a time-limited bearer token for an authenticated application user."""
    return create_signed_token(
        {**data, "purpose": "access"},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_signed_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    """Sign short-lived internal data, including OAuth state, with the app secret."""
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )


def decode_signed_token(token: str) -> dict[str, Any] | None:
    """Decode a signed token and return None when it is malformed or expired."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None


def encrypt_provider_token(value: str) -> str:
    """Encrypt an OAuth token before it is placed in the database."""
    if not settings.MAIL_TOKEN_ENCRYPTION_KEY:
        raise ValueError("MAIL_TOKEN_ENCRYPTION_KEY is not configured")
    return Fernet(settings.MAIL_TOKEN_ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()


def decrypt_provider_token(value: str) -> str:
    """Decrypt an OAuth token fetched from the database for a provider request."""
    if not settings.MAIL_TOKEN_ENCRYPTION_KEY:
        raise ValueError("MAIL_TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(settings.MAIL_TOKEN_ENCRYPTION_KEY.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored email-account credentials cannot be decrypted") from exc
