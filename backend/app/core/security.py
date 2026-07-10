from passlib.context import CryptContext

from jose import jwt

from datetime import timezone
from datetime import timedelta

from app.core.config import settings


pwd_context=CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def hash_password(password):

    return pwd_context.hash(password)


def verify_password(password,hashed):

    return pwd_context.verify(password,hashed)


def create_access_token(data):

    to_encode=data.copy()

    expire=timezone.utc.now()+timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp":expire})

    token=jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )

    return token