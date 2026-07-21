"""User contact settings and Meta WhatsApp Cloud API webhook endpoints."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.whatsapp_contact_repository import WhatsAppContactRepository
from app.schemas.whatsapp import (
    WhatsAppContactRequest,
    WhatsAppContactResponse,
    WhatsAppDispatchResponse,
)
from app.services.whatsapp_service import WhatsAppError, WhatsAppService


router = APIRouter()


@router.get("/contact", response_model=WhatsAppContactResponse | None)
async def get_whatsapp_contact(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the signed-in user's current WhatsApp delivery contact, if configured."""
    return await WhatsAppContactRepository(db).get_for_user(current_user.id)


@router.put("/contact", response_model=WhatsAppContactResponse)
async def save_whatsapp_contact(
    request: WhatsAppContactRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save an explicitly opted-in WhatsApp number for priority-email delivery."""
    try:
        return await WhatsAppService(db).save_contact(
            current_user.id, request.phone_number, request.opt_in
        )
    except WhatsAppError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.delete("/contact", status_code=status.HTTP_204_NO_CONTENT)
async def opt_out_whatsapp_contact(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Pause proactive WhatsApp alerts while preserving the contact's audit history."""
    contact = await WhatsAppContactRepository(db).get_for_user(current_user.id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "WhatsApp contact not found")
    contact.is_opted_in = False
    await WhatsAppContactRepository(db).save(contact)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/dispatch", response_model=WhatsAppDispatchResponse)
async def dispatch_whatsapp_notifications(
    retry_failed: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attempt delivery of the signed-in user's queued priority-email alerts."""
    try:
        return (await WhatsAppService(db).dispatch_for_user(
            current_user.id, retry_failed
        )).as_dict()
    except WhatsAppError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get("/webhook")
async def verify_whatsapp_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Complete Meta's webhook subscription challenge without user authentication."""
    verified_challenge = WhatsAppService.verify_webhook_challenge(
        mode, verify_token, challenge
    )
    if verified_challenge is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook verification failed")
    return Response(content=verified_challenge, media_type="text/plain")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Validate and process Meta delivery receipts and inbound WhatsApp commands."""
    raw_body = await request.body()
    service = WhatsAppService(db)
    if not service.validate_webhook_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook signature is invalid")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook payload is invalid") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook payload is invalid")
    await service.process_webhook_payload(payload)
    return {"status": "ok"}
