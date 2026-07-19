"""Authenticated APIs for connecting, listing, syncing, and removing inboxes."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.monitored_email_account_repository import MonitoredEmailAccountRepository
from app.schemas.email_account import (
    MonitoredEmailAccountResponse,
    OAuthStartResponse,
    SyncResultResponse,
)
from app.services.mail_oauth_service import MailOAuthError, MailOAuthService
from app.services.mail_sync_service import MailSyncError, MailSyncService


router = APIRouter()
Provider = Literal["gmail", "outlook"]


@router.get("/", response_model=list[MonitoredEmailAccountResponse])
async def list_email_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List every Gmail or Outlook inbox the signed-in user has connected."""
    return await MonitoredEmailAccountRepository(db).list_for_user(current_user.id)


@router.get("/oauth/{provider}/start", response_model=OAuthStartResponse)
async def start_email_connection(
    provider: Provider,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate the provider consent link for a new monitored inbox."""
    try:
        authorization_url = MailOAuthService(db).build_authorization_url(provider, current_user.id)
    except MailOAuthError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"provider": provider, "authorization_url": authorization_url}


@router.get("/oauth/{provider}/callback", response_model=MonitoredEmailAccountResponse)
async def complete_email_connection(
    provider: Provider,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Complete the provider redirect and save the newly authorized inbox."""
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error_description or error)
    if not code or not state:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Missing OAuth code or state")
    try:
        return await MailOAuthService(db).complete_connection(provider, code, state)
    except MailOAuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{account_id}/sync", response_model=SyncResultResponse)
async def sync_email_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch one of the user's connected inboxes and refresh its priority results."""
    account = await MonitoredEmailAccountRepository(db).get_by_id_for_user(account_id, current_user.id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email account not found")
    try:
        return (await MailSyncService(db).sync_account(account)).as_dict()
    except MailSyncError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stop monitoring an inbox by deleting its local connection and fetched data."""
    repository = MonitoredEmailAccountRepository(db)
    account = await repository.get_by_id_for_user(account_id, current_user.id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email account not found")
    await repository.delete(account)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
