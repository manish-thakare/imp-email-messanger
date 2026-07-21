"""Focused tests for WhatsApp webhook verification without external API calls."""

import hashlib
import hmac
import os
import unittest

# Supply the settings required when importing the application configuration.
os.environ.setdefault("APP_NAME", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:password@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from app.core.config import settings
from app.services.whatsapp_service import WhatsAppService


class WhatsAppWebhookTests(unittest.TestCase):
    """Verify that only Meta requests with matching secrets pass webhook checks."""

    def setUp(self) -> None:
        """Install temporary webhook secrets without changing the developer's .env file."""
        self.verify_token = settings.WHATSAPP_VERIFY_TOKEN
        self.app_secret = settings.WHATSAPP_APP_SECRET
        settings.WHATSAPP_VERIFY_TOKEN = "verify-secret"
        settings.WHATSAPP_APP_SECRET = "app-secret"

    def tearDown(self) -> None:
        """Restore shared settings after each isolated webhook test."""
        settings.WHATSAPP_VERIFY_TOKEN = self.verify_token
        settings.WHATSAPP_APP_SECRET = self.app_secret

    def test_valid_challenge_returns_meta_value(self) -> None:
        """A correct verification token should return Meta's raw challenge string."""
        result = WhatsAppService.verify_webhook_challenge(
            "subscribe", "verify-secret", "challenge-value"
        )
        self.assertEqual(result, "challenge-value")

    def test_invalid_challenge_is_rejected(self) -> None:
        """A mismatched verification token must not subscribe a third-party webhook."""
        result = WhatsAppService.verify_webhook_challenge(
            "subscribe", "incorrect", "challenge-value"
        )
        self.assertIsNone(result)

    def test_hmac_signature_validation(self) -> None:
        """Only the HMAC calculated with the configured app secret validates."""
        body = b'{"object":"whatsapp_business_account"}'
        signature = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(WhatsAppService.validate_webhook_signature(body, f"sha256={signature}"))
        self.assertFalse(WhatsAppService.validate_webhook_signature(body, "sha256=wrong"))
