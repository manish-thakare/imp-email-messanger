"""Fetch Gmail and Outlook inboxes, normalize messages, and classify priority."""

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.email_message import EmailMessage
from app.models.monitored_email_account import MonitoredEmailAccount
from app.repositories.email_message_repository import EmailMessageRepository
from app.repositories.monitored_email_account_repository import MonitoredEmailAccountRepository
from app.services.mail_oauth_service import MailOAuthError, MailOAuthService
from app.services.priority_service import EmailPriorityService
from app.services.whatsapp_service import WhatsAppError, WhatsAppService


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


@dataclass(frozen=True)
class FetchedMessages:
    """A provider page plus the durable cursor for the next incremental sync."""

    messages: list[dict[str, Any]]
    next_cursor: str


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
        """Fetch one connected inbox and persist priority assessments when inputs changed."""
        account_id = account.id
        try:
            access_token = await self.oauth_service.get_valid_access_token(account)
            if account.provider == "gmail":
                fetched = await self._fetch_gmail_messages(account, access_token)
            elif account.provider == "outlook":
                fetched = await self._fetch_outlook_messages(account, access_token)
            else:
                raise MailSyncError("This email provider is not supported")

            created_count = 0
            priority_count = 0
            new_priority_messages: list[EmailMessage] = []
            for message_data in fetched.messages:
                existing_message = await self.message_repo.get_by_provider_message_id(
                    account.id, message_data["provider_message_id"]
                )
                target_fingerprint = self.priority_service.classification_fingerprint(
                    message_data["subject"],
                    message_data.get("sender"),
                    message_data.get("body_preview"),
                )
                was_priority = bool(existing_message and existing_message.is_priority)
                if (
                    existing_message is not None
                    and existing_message.classification_fingerprint == target_fingerprint
                ):
                    priority_data = {
                        "priority_score": existing_message.priority_score,
                        "priority_label": existing_message.priority_label,
                        "is_priority": existing_message.is_priority,
                        "priority_reason": existing_message.priority_reason,
                        "classification_source": existing_message.classification_source,
                        "classification_fingerprint": existing_message.classification_fingerprint,
                    }
                else:
                    assessment = await self.priority_service.classify(
                        message_data["subject"],
                        message_data.get("sender"),
                        message_data.get("body_preview"),
                    )
                    priority_data = assessment.as_storage_dict(
                        self.priority_service.classification_fingerprint(
                            message_data["subject"],
                            message_data.get("sender"),
                            message_data.get("body_preview"),
                            source=assessment.source,
                        )
                    )
                stored_message, is_new = await self.message_repo.upsert(
                    account.id, message_data, priority_data
                )
                created_count += int(is_new)
                priority_count += int(stored_message.is_priority)
                if stored_message.is_priority and (is_new or not was_priority):
                    new_priority_messages.append(stored_message)

            account.last_synced_at = datetime.now(timezone.utc)
            account.sync_cursor = fetched.next_cursor
            account.status = "active"
            account.error_message = None
            await self.message_repo.commit()
            await self._dispatch_whatsapp_notifications(account.user_id, new_priority_messages)
            return SyncResult(
                account_id=account.id,
                fetched_count=len(fetched.messages),
                created_count=created_count,
                updated_count=len(fetched.messages) - created_count,
                priority_count=priority_count,
            )
        except (MailOAuthError, MailSyncError, httpx.HTTPError, ValueError) as exc:
            await self._record_sync_failure(account_id, str(exc))
            raise MailSyncError(str(exc)) from exc

    async def _dispatch_whatsapp_notifications(
        self, user_id: int, new_priority_messages: list[EmailMessage]
    ) -> None:
        """Queue new alerts and retry the user's eligible WhatsApp deliveries."""
        if not settings.WHATSAPP_ENABLED:
            return
        try:
            service = WhatsAppService(self.db)
            await service.queue_priority_notifications(user_id, new_priority_messages)
            await service.dispatch_for_user(user_id, retry_failed=True)
        except WhatsAppError as exc:
            logger.warning("WhatsApp notification dispatch skipped for user %s: %s", user_id, exc)

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
    ) -> FetchedMessages:
        """Fetch the next Gmail History API page, or establish an initial history cursor."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                cursor = _read_provider_cursor(account.sync_cursor, "gmail")
                if cursor.get("history_id"):
                    return await self._fetch_gmail_history_page(client, headers, cursor)
                return await self._fetch_gmail_initial_page(client, headers)
            except (httpx.HTTPError, KeyError, TypeError) as exc:
                raise MailSyncError("Unable to retrieve Gmail messages") from exc

    async def _fetch_gmail_initial_page(
        self, client: httpx.AsyncClient, headers: dict[str, str]
    ) -> FetchedMessages:
        """Import a bounded recent inbox page before using Gmail's incremental history feed."""
        response = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"labelIds": "INBOX", "maxResults": _provider_batch_size(500)},
        )
        response.raise_for_status()
        data = response.json()
        message_refs = data.get("messages", [])
        if not isinstance(message_refs, list):
            raise MailSyncError("Gmail returned an invalid message response")
        messages = await self._fetch_gmail_message_details(client, headers, message_refs)

        profile_response = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=headers
        )
        profile_response.raise_for_status()
        history_id = profile_response.json().get("historyId")
        if not isinstance(history_id, str):
            raise MailSyncError("Gmail did not return a sync cursor")
        return FetchedMessages(messages, _write_provider_cursor("gmail", history_id=history_id))

    async def _fetch_gmail_history_page(
        self, client: httpx.AsyncClient, headers: dict[str, str], cursor: dict[str, str]
    ) -> FetchedMessages:
        """Read one Gmail history page without dropping overflow into the next sync."""
        params: dict[str, str] = {
            "startHistoryId": cursor["history_id"],
            "historyTypes": "messageAdded",
            "maxResults": str(_provider_batch_size(500)),
        }
        if cursor.get("page_token"):
            params["pageToken"] = cursor["page_token"]
        response = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/history",
            headers=headers,
            params=params,
        )
        # Gmail history IDs expire after a limited retention period. Re-baseline safely.
        if response.status_code == 404:
            logger.info("Gmail history cursor expired; establishing a fresh cursor")
            return await self._fetch_gmail_initial_page(client, headers)
        response.raise_for_status()
        data = response.json()
        history = data.get("history", [])
        if not isinstance(history, list):
            raise MailSyncError("Gmail returned an invalid history response")
        messages = await self._fetch_gmail_message_details(
            client, headers, _gmail_history_message_refs(history)
        )
        next_page_token = data.get("nextPageToken")
        if isinstance(next_page_token, str) and next_page_token:
            next_cursor = _write_provider_cursor(
                "gmail", history_id=cursor["history_id"], page_token=next_page_token
            )
        else:
            history_id = data.get("historyId")
            if not isinstance(history_id, str):
                raise MailSyncError("Gmail did not return a sync cursor")
            next_cursor = _write_provider_cursor("gmail", history_id=history_id)
        return FetchedMessages(messages, next_cursor)

    async def _fetch_gmail_message_details(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        message_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Expand Gmail references while tolerating messages removed mid-sync."""
        messages = []
        for message_ref in message_refs:
            message_id = message_ref.get("id")
            if not isinstance(message_id, str):
                continue
            detail_response = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                headers=headers,
                params={"format": "full"},
            )
            if detail_response.status_code == 404:
                continue
            detail_response.raise_for_status()
            messages.append(_normalize_gmail_message(detail_response.json()))
        return messages

    async def _fetch_outlook_messages(
        self, account: MonitoredEmailAccount, access_token: str
    ) -> FetchedMessages:
        """Fetch one Microsoft Graph delta page and preserve its opaque continuation URL."""
        headers = {"Authorization": f"Bearer {access_token}"}
        cursor = _read_provider_cursor(account.sync_cursor, "outlook")
        continuation_url = cursor.get("next_link") or cursor.get("delta_link")
        initial_delta_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta"
        params: dict[str, str] | None = None
        if continuation_url is None:
            continuation_url = initial_delta_url
            params = _outlook_delta_params()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(continuation_url, headers=headers, params=params)
                if response.status_code == 410 and cursor:
                    logger.info("Outlook delta cursor expired; establishing a fresh cursor")
                    response = await client.get(
                        initial_delta_url, headers=headers, params=_outlook_delta_params()
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MailSyncError("Unable to retrieve Outlook messages") from exc

        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("value"), list):
            raise MailSyncError("Outlook returned an invalid message response")
        next_link = data.get("@odata.nextLink")
        delta_link = data.get("@odata.deltaLink")
        if isinstance(next_link, str) and next_link:
            next_cursor = _write_provider_cursor("outlook", next_link=next_link)
        elif isinstance(delta_link, str) and delta_link:
            next_cursor = _write_provider_cursor("outlook", delta_link=delta_link)
        else:
            raise MailSyncError("Outlook did not return a sync cursor")
        messages = [
            _normalize_outlook_message(message)
            for message in data["value"]
            if isinstance(message, dict) and "@removed" not in message and isinstance(message.get("id"), str)
        ]
        return FetchedMessages(messages, next_cursor)


def _outlook_delta_params() -> dict[str, str]:
    """Return the initial Graph delta query. Continuation URLs already contain query state."""
    return {
        "$top": str(_provider_batch_size(1000)),
        "$select": "id,conversationId,subject,from,toRecipients,bodyPreview,receivedDateTime",
    }


def _provider_batch_size(provider_limit: int) -> int:
    """Keep one provider response bounded even when a local environment is misconfigured."""
    return max(1, min(provider_limit, settings.MAIL_SYNC_BATCH_SIZE))


def _write_provider_cursor(provider: str, **values: str) -> str:
    """Serialize provider cursors as opaque JSON rather than lossy timestamps."""
    return json.dumps({"provider": provider, **values}, separators=(",", ":"))


def _read_provider_cursor(value: str | None, provider: str) -> dict[str, str]:
    """Read a provider-owned cursor, ignoring legacy timestamp cursors safely."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict) or parsed.get("provider") != provider:
        return {}
    return {
        key: item for key, item in parsed.items()
        if key != "provider" and isinstance(item, str) and item
    }


def _gmail_history_message_refs(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate message additions that can appear in multiple Gmail history events."""
    refs = []
    seen_ids: set[str] = set()
    for event in history:
        if not isinstance(event, dict):
            continue
        for addition in event.get("messagesAdded", []):
            message = addition.get("message", {}) if isinstance(addition, dict) else {}
            message_id = message.get("id") if isinstance(message, dict) else None
            if isinstance(message_id, str) and message_id not in seen_ids:
                seen_ids.add(message_id)
                refs.append({"id": message_id})
    return refs


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
        super().__init__()
        self.fragments: list[str] = []

    def handle_data(self, data: str) -> None:
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
