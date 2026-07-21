"""Optional periodic worker that refreshes every active connected inbox."""

import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.logger import logger
from app.repositories.monitored_email_account_repository import MonitoredEmailAccountRepository
from app.services.mail_sync_service import MailSyncError, MailSyncService


async def run_mail_sync_worker(stop_event: asyncio.Event) -> None:
    """Sync active inboxes repeatedly, with one PostgreSQL worker across all replicas."""
    async with engine.connect() as connection:
        lock_result = await connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": settings.MAIL_SYNC_WORKER_LOCK_ID},
        )
        if not lock_result.scalar_one():
            logger.info("Email sync worker skipped because another application replica owns the lock")
            return

        logger.info("Email sync worker started")
        try:
            while not stop_event.is_set():
                await _sync_active_accounts()
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=max(30, settings.MAIL_SYNC_INTERVAL_SECONDS),
                    )
                except TimeoutError:
                    continue
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": settings.MAIL_SYNC_WORKER_LOCK_ID},
            )
            logger.info("Email sync worker stopped")


async def _sync_active_accounts() -> None:
    """Discover active inboxes and isolate each provider sync in its own database session."""
    async with SessionLocal() as discovery_session:
        account_ids = await MonitoredEmailAccountRepository(discovery_session).list_active_ids()

    for account_id in account_ids:
        async with SessionLocal() as session:
            repository = MonitoredEmailAccountRepository(session)
            account = await repository.get_by_id(account_id)
            if account is None:
                continue
            try:
                await MailSyncService(session).sync_account(account)
            except MailSyncError as exc:
                logger.warning("Email sync failed for account %s: %s", account_id, exc)
            except Exception:
                logger.exception("Unexpected email sync failure for account %s", account_id)
