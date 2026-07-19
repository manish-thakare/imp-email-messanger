"""Fetch Gmail and Outlook inboxes, normalize messages, and classify priority."""

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.monitored_email_account import MonitoredEmailAccount
from app.repositories.email_message_repository import EmailMessageRepository
from app.repositories.monitored_email_account_repository import MonitoredEmailAccountRepository
from app.services.mail_oauth_service import MailOAuthError, MailOAuthService
from app.services.priority_service import EmailPriorityService


class MailSyncError(ValueError):
    """A user-safe error raised when a provider inbox cannot be synchronized."""


@dataclass(frozen=True)
class SyncResult:
    """Counts produced by a single manual or background account sync."""

    account_id: int
    fetched_count: int
    created_count: int
    updated_count: int
    priority_count: int

    def as_dict(self) -> dict[str, int]:
        """Convert the sync outcome into the API response structure."""
        return {
            "account_id": self.account_id,
            "fetched_count": self.fetched_count,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "priority_count": self.priority_count,
        }


class MailSyncService:
    """Coordinate provider fetching, normalized storage, and priority classification."""

    def __init__(self, db: AsyncSession):
        """Share the caller's database session across account and message updates."""
        self.db = db
        self.account_repo = MonitoredEmailAccountRepository(db)
        self.message_repo = EmailMessageRepository(db)
        self.oauth_service = MailOAuthService(db)
        self.priority_service = EmailPriorityService()

    async def sync_account(self, account: MonitoredEmailAccount) -> SyncResult:
        """Fetch one connected inbox and persist the priority assessment for each message."""
        account_id = account.id
        try:
            access_token = await self.oauth_service.get_valid_access_token(account)
            if account.provider == "gmail":
                messages = await self._fetch_gmail_messages(account, access_token)
            elif account.provider == "outlook":
                messages = await self._fetch_outlook_messages(account, access_token)
            else:
                raise MailSyncError("This email provider is not supported")

            created_count = 0
            priority_count = 0
            for message_data in messages:
                assessment = await self.priority_service.classify(
                    message_data["subject"],
                    message_data.get("sender"),
                    message_data.get("body_preview"),
                )
                _, is_new = await self.message_repo.upsert(
                    account.id,
                    message_data,
                    assessment.as_storage_dict(),
                )
                created_count += int(is_new)
                priority_count += int(assessment.is_priority)

            account.last_synced_at = datetime.now(timezone.utc)
            account.sync_cursor = account.last_synced_at.isoformat()
            account.status = "active"
            account.error_message = None
            await self.message_repo.commit()
            return SyncResult(
                account_id=account.id,
                fetched_count=len(messages),
                created_count=created_count,
                updated_count=len(messages) - created_count,
                priority_count=priority_count,
            )
        except (MailOAuthError, MailSyncError, httpx.HTTPError, ValueError) as exc:
            await self._record_sync_failure(account_id, str(exc))
            raise MailSyncError(str(exc)) from exc

    async def _record_sync_failure(self, account_id: int, message: str) -> None:
        """Keep the account active for retry while recording the latest sync failure."""
        await self.db.rollback()
        account = await self.account_repo.get_by_id(account_id)
        if account is None:
            return
        account.error_message = message[:1000]
        await self.db.commit()

    async def _fetch_gmail_messages(
        self, account: MonitoredEmailAccount, access_token: str
    ) -> list[dict[str, Any]]:
        """Fetch recent Gmail inbox messages and expand each message's MIME payload."""
        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, Any] = {
            "labelIds": "INBOX",
            "maxResults": settings.MAIL_SYNC_BATCH_SIZE,
        }
        cursor = _parse_cursor(account.sync_cursor)
        if cursor:
            params["q"] = f"after:{cursor.strftime('%Y/%m/%d')}"

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                message_refs = response.json().get("messages", [])
                messages = []
                for message_ref in message_refs:
                    detail_response = await client.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_ref['id']}",
                        headers=headers,
                        params={"format": "full"},
                    )
                    detail_response.raise_for_status()
                    messages.append(_normalize_gmail_message(detail_response.json()))
            except (httpx.HTTPError, KeyError, TypeError) as exc:
                raise MailSyncError("Unable to retrieve Gmail messages") from exc
        return messages

    async def _fetch_outlook_messages(
        self, account: MonitoredEmailAccount, access_token: str
    ) -> list[dict[str, Any]]:
        """Fetch recent Outlook inbox messages through Microsoft Graph."""
        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, str] = {
            "$top": str(settings.MAIL_SYNC_BATCH_SIZE),
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,toRecipients,bodyPreview,receivedDateTime",
        }
        cursor = _parse_cursor(account.sync_cursor)
        if cursor:
            params["$filter"] = f"receivedDateTime ge {cursor.isoformat().replace('+00:00', 'Z')}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MailSyncError("Unable to retrieve Outlook messages") from exc

        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("value"), list):
            raise MailSyncError("Outlook returned an invalid message response")
        return [_normalize_outlook_message(message) for message in data["value"]]


def _normalize_gmail_message(message: dict[str, Any]) -> dict[str, Any]:
    """Convert a Gmail API payload into fields used by the shared message model."""
    payload = message.get("payload", {})
    headers = {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in payload.get("headers", [])
        if isinstance(item, dict)
    }
    body = _extract_gmail_body(payload) or str(message.get("snippet", ""))
    return {
        "provider_message_id": str(message["id"]),
        "provider_thread_id": str(message.get("threadId")) if message.get("threadId") else None,
        "subject": headers.get("subject") or "(No subject)",
        "sender": headers.get("from") or None,
        "recipients": headers.get("to") or None,
        "body_preview": _compact_text(body, 8000) or None,
        "received_at": _parse_email_date(headers.get("date")),
    }


def _normalize_outlook_message(message: dict[str, Any]) -> dict[str, Any]:
    """Convert a Microsoft Graph message payload into the shared message model."""
    sender = (message.get("from") or {}).get("emailAddress", {}).get("address")
    recipients = [
        item.get("emailAddress", {}).get("address")
        for item in message.get("toRecipients", [])
        if item.get("emailAddress", {}).get("address")
    ]
    return {
        "provider_message_id": str(message["id"]),
        "provider_thread_id": str(message.get("conversationId")) if message.get("conversationId") else None,
        "subject": str(message.get("subject") or "(No subject)"),
        "sender": str(sender) if sender else None,
        "recipients": ", ".join(recipients) or None,
        "body_preview": _compact_text(str(message.get("bodyPreview") or ""), 8000) or None,
        "received_at": _parse_graph_date(message.get("receivedDateTime")),
    }


def _extract_gmail_body(payload: dict[str, Any]) -> str:
    """Prefer plain-text MIME parts and fall back to cleaned HTML when needed."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def collect(part: dict[str, Any]) -> None:
        """Walk nested Gmail MIME parts and collect readable content."""
        data = (part.get("body") or {}).get("data")
        content = _decode_gmail_data(data) if isinstance(data, str) else ""
        if content:
            if part.get("mimeType") == "text/plain":
                plain_parts.append(content)
            elif part.get("mimeType") == "text/html":
                html_parts.append(content)
        for child in part.get("parts") or []:
            if isinstance(child, dict):
                collect(child)

    collect(payload)
    if plain_parts:
        return "\n".join(plain_parts)
    return _html_to_text("\n".join(html_parts)) if html_parts else ""


def _decode_gmail_data(value: str) -> str:
    """Decode Gmail's URL-safe base64 body content without failing the whole sync."""
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return ""


class _TextExtractor(HTMLParser):
    """Small standard-library HTML-to-text helper for Gmail HTML-only messages."""

    def __init__(self) -> None:
        """Initialize the collector for visible text fragments."""
        super().__init__()
        self.fragments: list[str] = []

    def handle_data(self, data: str) -> None:
        """Collect text content while HTMLParser skips the markup itself."""
        self.fragments.append(data)


def _html_to_text(value: str) -> str:
    """Convert HTML content to readable text without adding a heavy parser dependency."""
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(parser.fragments)


def _compact_text(value: str, maximum_length: int) -> str:
    """Normalize whitespace and cap stored body content to a bounded safe preview."""
    return " ".join(value.split())[:maximum_length]


def _parse_email_date(value: str | None) -> datetime | None:
    """Parse Gmail's RFC email date header into a timezone-aware timestamp."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def _parse_graph_date(value: object) -> datetime | None:
    """Parse Microsoft's ISO timestamp into a timezone-aware database timestamp."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_cursor(value: str | None) -> datetime | None:
    """Read the prior sync timestamp used to limit the next provider request."""
    return _parse_graph_date(value)
