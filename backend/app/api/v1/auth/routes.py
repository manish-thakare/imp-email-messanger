from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.auth import RegisterSchema
from app.schemas.auth import LoginSchema
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService

router=APIRouter()

#register route
@router.post("/register")
async def register(
    request: RegisterSchema,
    db: AsyncSession = Depends(get_db)
):
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
            400,
            str(exc)
        ) from exc
    return {
        "message": "registered",
        "username": user.username,
        "primary_email": user.primary_email
    }

#login route
@router.post("/login")
async def login(
    request: LoginSchema,
    db: AsyncSession = Depends(get_db)
):
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
        "access_token": token
    }
