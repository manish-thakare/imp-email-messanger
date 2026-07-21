"""Meta WhatsApp Cloud API delivery, webhook validation, and inbox chat commands."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.email_message import EmailMessage
from app.models.whatsapp_contact import WhatsAppContact
from app.repositories.email_message_repository import EmailMessageRepository
from app.repositories.whatsapp_contact_repository import WhatsAppContactRepository
from app.repositories.whatsapp_notification_repository import WhatsAppNotificationRepository


class WhatsAppError(ValueError):
    """A user-safe error raised when WhatsApp delivery cannot be completed."""


@dataclass(frozen=True)
class WhatsAppDispatchResult:
    """Counts produced while sending queued notifications for one user."""

    queued_count: int
    sent_count: int
    failed_count: int

    def as_dict(self) -> dict[str, int]:
        """Convert dispatch counts into the response shape used by the API."""
        return {
            "queued_count": self.queued_count,
            "sent_count": self.sent_count,
            "failed_count": self.failed_count,
        }


class WhatsAppService:
    """Manage WhatsApp opt-in contacts, priority alerts, and inbound chat replies."""

    def __init__(self, db: AsyncSession):
        """Share the request or worker database session across WhatsApp operations."""
        self.db = db
        self.contact_repo = WhatsAppContactRepository(db)
        self.notification_repo = WhatsAppNotificationRepository(db)
        self.message_repo = EmailMessageRepository(db)

    async def save_contact(
        self, user_id: int, phone_number: str, is_opted_in: bool
    ) -> WhatsAppContact:
        """Create or update the signed-in user's explicit WhatsApp delivery opt-in."""
        contact = await self.contact_repo.get_for_user(user_id)
        claimed_contact = await self.contact_repo.get_by_phone_number(phone_number)
        if claimed_contact is not None and claimed_contact.user_id != user_id:
            raise WhatsAppError("That WhatsApp number is already linked to another user")

        if contact is None:
            contact = WhatsAppContact(
                user_id=user_id,
                phone_number=phone_number,
                is_opted_in=is_opted_in,
            )
        else:
            contact.phone_number = phone_number
            contact.is_opted_in = is_opted_in
        return await self.contact_repo.save(contact)

    async def queue_priority_notifications(
        self, user_id: int, messages: list[EmailMessage]
    ) -> int:
        """Queue a single delivery record for each newly classified priority message."""
        contact = await self.contact_repo.get_for_user(user_id)
        if contact is None or not contact.is_opted_in:
            return 0

        queued_count = 0
        for message in messages:
            if message.id is None:
                continue
            _, created = await self.notification_repo.queue(user_id, message.id, contact.phone_number)
            queued_count += int(created)
        if queued_count:
            await self.db.commit()
        return queued_count

    async def dispatch_for_user(
        self, user_id: int, retry_failed: bool = False
    ) -> WhatsAppDispatchResult:
        """Send the user's queued alert templates and record each provider response."""
        self._require_delivery_configuration()
        deliveries = await self.notification_repo.list_for_delivery(
            user_id,
            retry_failed,
            max(1, settings.WHATSAPP_MAX_DELIVERY_ATTEMPTS),
        )
        sent_count = 0
        failed_count = 0

        for notification, message in deliveries:
            notification.attempt_count += 1
            try:
                provider_message_id = await self._send_priority_template(
                    notification.phone_number, message
                )
                notification.provider_message_id = provider_message_id
                notification.status = "sent"
                notification.sent_at = datetime.now(timezone.utc)
                notification.error_message = None
                sent_count += 1
            except WhatsAppError as exc:
                notification.status = "failed"
                notification.error_message = str(exc)[:1000]
                failed_count += 1
                logger.warning("WhatsApp delivery failed for notification %s: %s", notification.id, exc)
            await self.notification_repo.save(notification)

        return WhatsAppDispatchResult(len(deliveries), sent_count, failed_count)

    @staticmethod
    def verify_webhook_challenge(
        mode: str | None, verify_token: str | None, challenge: str | None
    ) -> str | None:
        """Return Meta's challenge only when the configured verification token matches."""
        if (
            mode == "subscribe"
            and challenge
            and settings.WHATSAPP_VERIFY_TOKEN
            and verify_token
            and hmac.compare_digest(verify_token, settings.WHATSAPP_VERIFY_TOKEN)
        ):
            return challenge
        return None

    @staticmethod
    def validate_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
        """Validate Meta's HMAC SHA-256 webhook signature before reading its JSON body."""
        if not settings.WHATSAPP_APP_SECRET or not signature:
            return False
        expected = hmac.new(
            settings.WHATSAPP_APP_SECRET.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        received = signature.removeprefix("sha256=")
        return hmac.compare_digest(received, expected)

    async def process_webhook_payload(self, payload: dict[str, Any]) -> None:
        """Apply Meta delivery receipts and answer supported inbound user commands."""
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                await self._process_delivery_statuses(value.get("statuses", []))
                await self._process_inbound_messages(value.get("messages", []))

    async def _process_delivery_statuses(self, statuses: list[dict[str, Any]]) -> None:
        """Persist provider send, delivery, read, and failed status updates."""
        for status_data in statuses:
            provider_message_id = status_data.get("id")
            status = status_data.get("status")
            if not isinstance(provider_message_id, str) or status not in {
                "sent", "delivered", "read", "failed"
            }:
                continue
            occurred_at = _parse_unix_timestamp(status_data.get("timestamp"))
            await self.notification_repo.update_delivery_status(
                provider_message_id, status, occurred_at
            )

    async def _process_inbound_messages(self, messages: list[dict[str, Any]]) -> None:
        """Map an inbound WhatsApp message to its opted-in user and send a safe reply."""
        for message_data in messages:
            sender = message_data.get("from")
            if not isinstance(sender, str) or not sender.isdigit():
                continue
            contact = await self.contact_repo.get_by_phone_number(f"+{sender}")
            if contact is None:
                logger.info("Ignoring WhatsApp message from an unlinked number")
                continue

            contact.last_inbound_at = datetime.now(timezone.utc)
            reply = await self._reply_for_message(contact, message_data)
            await self.contact_repo.save(contact)
            if reply:
                try:
                    await self._send_text(contact.phone_number, reply)
                except WhatsAppError as exc:
                    logger.warning("WhatsApp chat reply failed for contact %s: %s", contact.id, exc)

    async def _reply_for_message(
        self, contact: WhatsAppContact, message_data: dict[str, Any]
    ) -> str | None:
        """Interpret a small command set without exposing any email to unknown senders."""
        if message_data.get("type") != "text":
            return "Reply LATEST to see important emails, or STOP to pause alerts."
        text = str((message_data.get("text") or {}).get("body") or "").strip().lower()

        if text in {"stop", "unsubscribe"}:
            contact.is_opted_in = False
            return "Priority-email alerts are paused. Reply START to enable them again."
        if text in {"start", "subscribe"}:
            contact.is_opted_in = True
            return "Priority-email alerts are enabled. Reply LATEST whenever you want a summary."
        if text in {"latest", "priority", "important"}:
            messages = await self.message_repo.list_for_user(
                contact.user_id, priority_only=True, limit=3, offset=0
            )
            return _format_priority_summary(messages)
        return "Reply LATEST for important emails, STOP to pause alerts, or START to resume them."

    async def _send_priority_template(self, phone_number: str, message: EmailMessage) -> str:
        """Send the approved proactive alert template without exposing a full email body."""
        payload = {
            "messaging_product": "whatsapp",
            "to": _provider_phone_number(phone_number),
            "type": "template",
            "template": {
                "name": settings.WHATSAPP_PRIORITY_TEMPLATE_NAME,
                "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": _short_text(message.sender or "Unknown sender", 120)},
                            {"type": "text", "text": _short_text(message.subject, 300)},
                            {"type": "text", "text": _short_text(message.priority_reason or "Important email", 300)},
                        ],
                    }
                ],
            },
        }
        return await self._post_message(payload)

    async def _send_text(self, phone_number: str, text: str) -> str:
        """Reply to an inbound user command inside WhatsApp's customer-service window."""
        self._require_delivery_configuration()
        payload = {
            "messaging_product": "whatsapp",
            "to": _provider_phone_number(phone_number),
            "type": "text",
            "text": {"preview_url": False, "body": _short_text(text, 4000)},
        }
        return await self._post_message(payload)

    async def _post_message(self, payload: dict[str, Any]) -> str:
        """Send a Cloud API message and return Meta's outbound message identifier."""
        self._require_delivery_configuration()
        endpoint = (
            f"https://graph.facebook.com/{settings.WHATSAPP_GRAPH_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WhatsAppError("WhatsApp could not accept the message") from exc

        try:
            provider_message_id = response.json()["messages"][0]["id"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WhatsAppError("WhatsApp returned an invalid message response") from exc
        if not isinstance(provider_message_id, str):
            raise WhatsAppError("WhatsApp returned an invalid message identifier")
        return provider_message_id

    def _require_delivery_configuration(self) -> None:
        """Fail before outbound delivery when Meta Cloud API settings are incomplete."""
        required_settings = {
            "WHATSAPP_ENABLED": settings.WHATSAPP_ENABLED,
            "WHATSAPP_GRAPH_API_VERSION": settings.WHATSAPP_GRAPH_API_VERSION,
            "WHATSAPP_PHONE_NUMBER_ID": settings.WHATSAPP_PHONE_NUMBER_ID,
            "WHATSAPP_ACCESS_TOKEN": settings.WHATSAPP_ACCESS_TOKEN,
            "WHATSAPP_PRIORITY_TEMPLATE_NAME": settings.WHATSAPP_PRIORITY_TEMPLATE_NAME,
        }
        missing = [name for name, value in required_settings.items() if not value]
        if missing:
            raise WhatsAppError("WhatsApp delivery is not configured")


def _provider_phone_number(phone_number: str) -> str:
    """Convert a stored E.164 number into the digits-only Cloud API recipient value."""
    return phone_number.removeprefix("+")


def _parse_unix_timestamp(value: object) -> datetime | None:
    """Convert a webhook epoch timestamp into a timezone-aware database timestamp."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _short_text(value: str, maximum_length: int) -> str:
    """Normalize and bound text passed to provider templates or chat replies."""
    return " ".join(value.split())[:maximum_length]


def _format_priority_summary(messages: list[EmailMessage]) -> str:
    """Build a compact, privacy-conscious WhatsApp reply from the user's top messages."""
    if not messages:
        return "You have no high-priority emails right now."
    items = [
        f"{index}. {_short_text(message.subject, 120)} - {_short_text(message.sender or 'Unknown sender', 80)}"
        for index, message in enumerate(messages, start=1)
    ]
    return "Your important emails:\n" + "\n".join(items)
