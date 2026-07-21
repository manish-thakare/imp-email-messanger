"""Database operations for fetched messages and the priority feed."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_message import EmailMessage
from app.models.monitored_email_account import MonitoredEmailAccount


class EmailMessageRepository:
    """Store provider messages and return only the messages owned by a user."""

    def __init__(self, db: AsyncSession):
        """Use the database session shared with the current sync operation."""
        self.db = db

    async def upsert(
        self,
        account_id: int,
        message_data: dict[str, Any],
        priority_data: dict[str, Any]
    ) -> tuple[EmailMessage, bool]:
        """Create or refresh a provider message without duplicating it on later syncs."""
        result = await self.db.execute(
            select(EmailMessage).where(
                EmailMessage.account_id == account_id,
                EmailMessage.provider_message_id == message_data["provider_message_id"]
            )
        )
        message = result.scalar_one_or_none()
        is_new = message is None

        if message is None:
            message = EmailMessage(
                account_id=account_id,
                provider_message_id=message_data["provider_message_id"]
            )
            self.db.add(message)

        for field, value in message_data.items():
            if field != "provider_message_id":
                setattr(message, field, value)
        for field, value in priority_data.items():
            setattr(message, field, value)
        return message, is_new

    async def get_by_provider_message_id(
        self, account_id: int, provider_message_id: str
    ) -> EmailMessage | None:
        """Return an existing provider message before deciding whether to reclassify it."""
        result = await self.db.execute(
            select(EmailMessage).where(
                EmailMessage.account_id == account_id,
                EmailMessage.provider_message_id == provider_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: int, priority_only: bool, limit: int, offset: int
    ) -> list[EmailMessage]:
        """List messages from every inbox the user owns, ordered by importance then time."""
        statement = (
            select(EmailMessage)
            .join(MonitoredEmailAccount)
            .where(MonitoredEmailAccount.user_id == user_id)
            .order_by(EmailMessage.priority_score.desc(), EmailMessage.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if priority_only:
            statement = statement.where(EmailMessage.is_priority.is_(True))
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def get_for_user(self, message_id: int, user_id: int) -> EmailMessage | None:
        """Retrieve one message only when its source inbox belongs to the user."""
        result = await self.db.execute(
            select(EmailMessage)
            .join(MonitoredEmailAccount)
            .where(
                EmailMessage.id == message_id,
                MonitoredEmailAccount.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def commit(self) -> None:
        """Persist all message changes collected during a provider sync."""
        await self.db.commit()
