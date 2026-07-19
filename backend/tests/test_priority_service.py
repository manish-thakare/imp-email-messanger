"""Focused tests for the email importance rules that work without external services."""

import os
import unittest

# Supply the settings required when importing the application configuration.
os.environ.setdefault("APP_NAME", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from app.services.priority_service import EmailPriorityService


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
