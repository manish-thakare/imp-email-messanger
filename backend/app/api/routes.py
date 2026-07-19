from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.auth import RegisterSchema
from app.schemas.auth import LoginSchema
from app.schemas.auth import AccessTokenResponse
from app.schemas.auth import UserResponse
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: RegisterSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a user account identified by a unique username and primary email."""
    repo = UserRepository(db)
    service = AuthService(repo)
    try:
        user = await service.register(
            request.username,
            request.primary_email,
            request.password
        )
    except ValueError as exc:
        raise HTTPException(
            409,
            str(exc)
        ) from exc
    return user

@router.post("/login", response_model=AccessTokenResponse)
async def login(
    request: LoginSchema,
    db: AsyncSession = Depends(get_db)
):
    """Sign in with a username and password, returning a bearer token."""
    repo = UserRepository(db)
    service = AuthService(repo)
    token = await service.login(
        request.username,
        request.password
    )
    if token is None:
        raise HTTPException(
            401,
            "Invalid credentials"
        )
    return {
        "access_token": token,
        "token_type": "bearer"
    }
