"""Database operations for the durable WhatsApp priority-alert outbox."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_message import EmailMessage
from app.models.whatsapp_notification import WhatsAppNotification


class WhatsAppNotificationRepository:
    """Queue, dispatch, and track a single WhatsApp alert for each priority email."""

    def __init__(self, db: AsyncSession):
        """Use the database session shared by the sync or webhook handler."""
        self.db = db

    async def queue(
        self, user_id: int, email_message_id: int, phone_number: str, payload_json: str
    ) -> tuple[WhatsAppNotification, bool]:
        """Create one pending notification unless that email was already queued."""
        result = await self.db.execute(
            insert(WhatsAppNotification)
            .values(
                user_id=user_id,
                email_message_id=email_message_id,
                phone_number=phone_number,
                payload_json=payload_json,
                status="pending",
            )
            .on_conflict_do_nothing(index_elements=[WhatsAppNotification.email_message_id])
            .returning(WhatsAppNotification)
        )
        notification = result.scalar_one_or_none()
        if notification is not None:
            return notification, True
        existing = await self.db.execute(
            select(WhatsAppNotification).where(
                WhatsAppNotification.email_message_id == email_message_id
            )
        )
        return existing.scalar_one(), False

    async def list_for_delivery(
        self, user_id: int, include_failed: bool = False, max_attempts: int = 5
    ) -> list[tuple[WhatsAppNotification, EmailMessage]]:
        """Return queued alerts with the source message needed for template variables."""
        statuses = ["pending", "failed"] if include_failed else ["pending"]
        result = await self.db.execute(
            select(WhatsAppNotification, EmailMessage)
            .join(EmailMessage, EmailMessage.id == WhatsAppNotification.email_message_id)
            .where(
                WhatsAppNotification.user_id == user_id,
                WhatsAppNotification.status.in_(statuses),
                WhatsAppNotification.attempt_count < max_attempts,
            )
            .order_by(WhatsAppNotification.created_at.asc())
        )
        return list(result.all())

    async def get_by_provider_message_id(
        self, provider_message_id: str
    ) -> WhatsAppNotification | None:
        """Find an outbound alert from Meta's delivery-status webhook identifier."""
        result = await self.db.execute(
            select(WhatsAppNotification).where(
                WhatsAppNotification.provider_message_id == provider_message_id
            )
        )
        return result.scalar_one_or_none()

    async def save(self, notification: WhatsAppNotification) -> WhatsAppNotification:
        """Commit the latest send attempt or delivery status for one alert."""
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def update_delivery_status(
        self, provider_message_id: str, status: str, occurred_at: datetime | None
    ) -> None:
        """Record Meta's sent, delivered, read, or failed status without creating alerts."""
        notification = await self.get_by_provider_message_id(provider_message_id)
        if notification is None:
            return
        notification.status = status
        if status == "delivered":
            notification.delivered_at = occurred_at
        elif status == "read":
            notification.read_at = occurred_at
        await self.db.commit()
