"""Authenticated prioritized inbox feed APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.email_message_repository import EmailMessageRepository
from app.schemas.email_message import EmailMessageResponse


router = APIRouter()


@router.get("/", response_model=list[EmailMessageResponse])
async def list_messages(
    priority_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return messages from all user inboxes, optionally showing only high priority items."""
    return await EmailMessageRepository(db).list_for_user(
        current_user.id, priority_only, limit, offset
    )


@router.get("/priority", response_model=list[EmailMessageResponse])
async def list_priority_messages(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return only high-priority messages for the combined chatbot-style feed."""
    return await EmailMessageRepository(db).list_for_user(
        current_user.id, True, limit, offset
    )


@router.get("/{message_id}", response_model=EmailMessageResponse)
async def get_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a single fetched message after verifying it belongs to the current user."""
    message = await EmailMessageRepository(db).get_for_user(message_id, current_user.id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email message not found")
    return message
