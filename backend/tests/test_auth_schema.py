"""Tests for the registration contract after WhatsApp contact normalization."""

import os
import unittest

from pydantic import ValidationError


os.environ.setdefault("APP_NAME", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:password@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from app.schemas.auth import RegisterSchema


class RegisterSchemaTests(unittest.TestCase):
    def test_phone_number_is_not_accepted_on_user_registration(self) -> None:
        """WhatsApp numbers must be submitted through the explicit opt-in endpoint."""
        with self.assertRaises(ValidationError):
            RegisterSchema(
                username="tester",
                primary_email="tester@example.com",
                password="strong-password",
                phone_number="+14155552671",
            )
