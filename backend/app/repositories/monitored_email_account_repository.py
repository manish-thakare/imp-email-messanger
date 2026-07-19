"""Database operations for OAuth-connected inboxes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitored_email_account import MonitoredEmailAccount


class MonitoredEmailAccountRepository:
    """Persist and retrieve inboxes while enforcing their owner boundaries."""

    def __init__(self, db: AsyncSession):
        """Use the request or worker database session supplied by the caller."""
        self.db = db

    async def get_by_id(self, account_id: int) -> MonitoredEmailAccount | None:
        """Find an inbox by its internal identifier for worker processing."""
        result = await self.db.execute(
            select(MonitoredEmailAccount).where(MonitoredEmailAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(
        self, account_id: int, user_id: int
    ) -> MonitoredEmailAccount | None:
        """Find an inbox only when it belongs to the supplied application user."""
        result = await self.db.execute(
            select(MonitoredEmailAccount).where(
                MonitoredEmailAccount.id == account_id,
                MonitoredEmailAccount.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_provider_email(
        self, provider: str, email_address: str
    ) -> MonitoredEmailAccount | None:
        """Find a provider inbox to prevent two users claiming the same credentials."""
        result = await self.db.execute(
            select(MonitoredEmailAccount).where(
                MonitoredEmailAccount.provider == provider,
                MonitoredEmailAccount.email_address == email_address.lower()
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[MonitoredEmailAccount]:
        """Return all connected inboxes belonging to one user, newest first."""
        result = await self.db.execute(
            select(MonitoredEmailAccount)
            .where(MonitoredEmailAccount.user_id == user_id)
            .order_by(MonitoredEmailAccount.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_ids(self) -> list[int]:
        """Return active inbox identifiers for the periodic sync worker."""
        result = await self.db.execute(
            select(MonitoredEmailAccount.id).where(MonitoredEmailAccount.status == "active")
        )
        return list(result.scalars().all())

    async def create(self, account: MonitoredEmailAccount) -> MonitoredEmailAccount:
        """Store a newly authorized inbox and populate its database identifier."""
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def save(self, account: MonitoredEmailAccount) -> MonitoredEmailAccount:
        """Commit changed inbox credentials or sync state."""
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def delete(self, account: MonitoredEmailAccount) -> None:
        """Remove an inbox and its fetched messages from the local database."""
        await self.db.delete(account)
        await self.db.commit()
