"""Database operations for user-owned WhatsApp delivery contacts."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp_contact import WhatsAppContact


class WhatsAppContactRepository:
    """Persist contacts and look them up safely by user or inbound phone number."""

    def __init__(self, db: AsyncSession):
        """Use the request or worker session supplied by the caller."""
        self.db = db

    async def get_for_user(self, user_id: int) -> WhatsAppContact | None:
        """Return the one WhatsApp contact registered by a user."""
        result = await self.db.execute(
            select(WhatsAppContact).where(WhatsAppContact.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone_number(self, phone_number: str) -> WhatsAppContact | None:
        """Find a contact from Meta's inbound sender number."""
        result = await self.db.execute(
            select(WhatsAppContact).where(WhatsAppContact.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def save(self, contact: WhatsAppContact) -> WhatsAppContact:
        """Commit a contact update and return the current persisted state."""
        self.db.add(contact)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact
