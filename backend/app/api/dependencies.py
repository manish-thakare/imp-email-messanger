"""Reusable dependencies that protect authenticated API routes."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_signed_token
from app.models.user import User
from app.repositories.user_repository import UserRepository


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Resolve the bearer token into the current user or reject the request."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required")

    payload = decode_signed_token(credentials.credentials)
    username = payload.get("sub") if payload else None
    if not payload or payload.get("purpose") != "access" or not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token")

    user = await UserRepository(db).get_by_username(username)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User account no longer exists")
    return user
