"""Tests for bounded notification payloads and predefined WhatsApp routing."""

import os
import unittest
from unittest.mock import AsyncMock


os.environ.setdefault("APP_NAME", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:password@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from app.models.email_message import EmailMessage
from app.models.whatsapp_contact import WhatsAppContact
from app.services.notification_builder import NotificationBuilder
from app.services.whatsapp_service import WhatsAppService
from app.services.whatsapp_command_router import PredefinedWhatsAppToolRouter


class NotificationAndCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_payload_is_bounded_and_round_trips(self) -> None:
        message = EmailMessage(
            sender="sender@example.com",
            subject="A subject",
            body_preview="x" * 1000,
            priority_label="high",
            priority_score=92,
            priority_reason="Security alert",
        )

        payload = NotificationBuilder.build(message)
        restored = payload.from_json(payload.as_json())

        self.assertEqual(restored.subject, "A subject")
        self.assertEqual(len(restored.summary), 180)
        self.assertNotIn("x" * 181, payload.as_text())

    async def test_whatsapp_template_uses_the_bounded_notification_payload(self) -> None:
        service = WhatsAppService(None)  # The HTTP method is replaced for this unit test.
        service._post_message = AsyncMock(return_value="provider-id")
        message = EmailMessage(
            sender="sender@example.com",
            subject="Subject",
            body_preview="private body",
            priority_label="high",
            priority_score=90,
            priority_reason="Security signal",
        )

        result = await service._send_priority_template(
            "+14155552671", NotificationBuilder.build(message)
        )

        self.assertEqual(result, "provider-id")
        request = service._post_message.await_args.args[0]
        parameters = request["template"]["components"][0]["parameters"]
        self.assertEqual(parameters[1]["text"], "Subject")
        self.assertNotIn("private body", str(request))

    async def test_router_accepts_only_predefined_aliases(self) -> None:
        contact = WhatsAppContact(user_id=7, phone_number="+14155552671", is_opted_in=True)
        calls: list[str] = []

        async def latest(_contact: WhatsAppContact) -> str:
            calls.append("latest")
            return "latest result"

        async def stop(_contact: WhatsAppContact) -> str:
            calls.append("stop")
            return "stop result"

        router = PredefinedWhatsAppToolRouter({"latest": latest, "stop": stop})

        self.assertEqual(await router.route("LATEST now", contact), "latest result")
        self.assertEqual(await router.route("STOP", contact), "stop result")
        self.assertIn("LATEST", await router.route("delete everything", contact))
        self.assertEqual(calls, ["latest", "stop"])
