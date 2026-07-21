"""Focused tests for the email importance rules that work without external services."""

import os
import unittest
from unittest.mock import patch

# Supply the settings required when importing the application configuration.
os.environ.setdefault("APP_NAME", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:password@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from app.core.config import settings
from app.services.priority_service import EmailPriorityService


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class _FakeAsyncClient:
    def __init__(self, response_payload: dict[str, object]):
        self.response_payload = response_payload
        self.request_payload: dict[str, object] | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> _FakeResponse:
        self.request_payload = json
        return _FakeResponse(self.response_payload)


class PriorityServiceTests(unittest.IsolatedAsyncioTestCase):
    """Verify the user-visible high-priority and low-priority outcomes."""

    async def test_security_alert_is_high_priority(self) -> None:
        """A security notice should reach the priority feed without an LLM."""
        assessment = await EmailPriorityService().classify(
            "Security alert: verify your password",
            "security@example.com",
            "Immediate action required to keep your account secure.",
        )
        self.assertTrue(assessment.is_priority)
        self.assertEqual(assessment.label, "high")
        self.assertEqual(assessment.source, "rules")

    async def test_newsletter_is_not_priority(self) -> None:
        """Routine marketing mail should stay out of the priority-only feed."""
        assessment = await EmailPriorityService().classify(
            "Weekly newsletter and special offer",
            "news@example.com",
            "Read our weekly digest. Unsubscribe at any time.",
        )
        self.assertFalse(assessment.is_priority)
        self.assertEqual(assessment.label, "low")

    async def test_llm_omits_email_body_until_explicitly_enabled(self) -> None:
        """The privacy default sends only the minimum fields required for triage."""
        original = {
            "enabled": settings.LLM_PRIORITY_ENABLED,
            "url": settings.LLM_PRIORITY_API_URL,
            "send_body": settings.LLM_PRIORITY_SEND_BODY_PREVIEW,
        }
        fake_client = _FakeAsyncClient({
            "choices": [{"message": {"content": '{"score": 88, "label": "high", "reason": "Security action needed"}'}}]
        })
        settings.LLM_PRIORITY_ENABLED = True
        settings.LLM_PRIORITY_API_URL = "https://llm.example.test/v1/chat/completions"
        settings.LLM_PRIORITY_SEND_BODY_PREVIEW = False
        try:
            with patch("app.services.priority_service.httpx.AsyncClient", return_value=fake_client):
                assessment = await EmailPriorityService().classify(
                    "Account security update", "security@example.com", "PRIVATE BODY CONTENT"
                )
        finally:
            settings.LLM_PRIORITY_ENABLED = original["enabled"]
            settings.LLM_PRIORITY_API_URL = original["url"]
            settings.LLM_PRIORITY_SEND_BODY_PREVIEW = original["send_body"]

        self.assertEqual(assessment.source, "llm")
        self.assertEqual(assessment.score, 88)
        self.assertIsNotNone(fake_client.request_payload)
        request_text = str(fake_client.request_payload)
        self.assertNotIn("PRIVATE BODY CONTENT", request_text)
        self.assertIn("Account security update", request_text)

    async def test_malformed_llm_response_falls_back_to_rules(self) -> None:
        """An invalid model result cannot create an invalid priority record."""
        original_enabled = settings.LLM_PRIORITY_ENABLED
        original_url = settings.LLM_PRIORITY_API_URL
        fake_client = _FakeAsyncClient({
            "choices": [{"message": {"content": '{"score": 999, "label": "high", "reason": "bad"}'}}]
        })
        settings.LLM_PRIORITY_ENABLED = True
        settings.LLM_PRIORITY_API_URL = "https://llm.example.test/v1/chat/completions"
        try:
            with patch("app.services.priority_service.httpx.AsyncClient", return_value=fake_client):
                assessment = await EmailPriorityService().classify(
                    "Security alert", "security@example.com", "Action required"
                )
        finally:
            settings.LLM_PRIORITY_ENABLED = original_enabled
            settings.LLM_PRIORITY_API_URL = original_url

        self.assertEqual(assessment.source, "rules")
        self.assertTrue(assessment.is_priority)
