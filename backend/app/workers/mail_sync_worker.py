"""Optional periodic worker that refreshes every active connected inbox."""

import asyncio

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.repositories.monitored_email_account_repository import MonitoredEmailAccountRepository
from app.services.mail_sync_service import MailSyncError, MailSyncService


async def run_mail_sync_worker(stop_event: asyncio.Event) -> None:
    """Sync active inboxes repeatedly until the application requests shutdown."""
    logger.info("Email sync worker started")
    while not stop_event.is_set():
        await _sync_active_accounts()
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(30, settings.MAIL_SYNC_INTERVAL_SECONDS),
            )
        except TimeoutError:
            continue
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
