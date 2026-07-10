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
    user = await service.register(
        request.username,
        request.email,
        request.password
    )
    return {
        "message": "registered",
        "user": user.email
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
        request.email,
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