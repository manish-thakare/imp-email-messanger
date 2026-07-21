"""Unit tests for provider-owned incremental sync cursor handling."""

import os
import unittest


os.environ.setdefault("APP_NAME", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:password@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from app.services.mail_sync_service import (
    _gmail_history_message_refs,
    _read_provider_cursor,
    _write_provider_cursor,
)


class SyncCursorTests(unittest.TestCase):
    def test_provider_cursor_round_trip(self) -> None:
        cursor = _write_provider_cursor("gmail", history_id="123", page_token="next")

        self.assertEqual(
            _read_provider_cursor(cursor, "gmail"),
            {"history_id": "123", "page_token": "next"},
        )
        self.assertEqual(_read_provider_cursor(cursor, "outlook"), {})

    def test_legacy_timestamp_cursor_is_discarded_for_safe_rebaseline(self) -> None:
        self.assertEqual(_read_provider_cursor("2026-07-20T10:00:00+00:00", "gmail"), {})

    def test_gmail_history_message_refs_are_deduplicated(self) -> None:
        history = [
            {"messagesAdded": [{"message": {"id": "a"}}, {"message": {"id": "b"}}]},
            {"messagesAdded": [{"message": {"id": "a"}}]},
        ]

        self.assertEqual(_gmail_history_message_refs(history), [{"id": "a"}, {"id": "b"}])
