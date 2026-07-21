"""Build bounded, reusable notification payloads from classified messages."""

from dataclasses import asdict, dataclass
import json

from app.models.email_message import EmailMessage


@dataclass(frozen=True)
class NotificationPayload:
    """Provider-neutral content used by queues, WhatsApp, and future channels."""

    title: str
    sender: str
    subject: str
    priority_label: str
    priority_score: int
    reason: str
    summary: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))

    def as_text(self) -> str:
        return (
            f"{self.title}\n"
            f"From: {self.sender}\n"
            f"Subject: {self.subject}\n"
            f"Priority: {self.priority_label.upper()} ({self.priority_score}/100)\n"
            f"Reason: {self.reason}\n"
            f"Summary: {self.summary}"
        )

    @classmethod
    def from_json(cls, value: str) -> "NotificationPayload":
        """Restore a queued payload while rejecting malformed persisted data."""
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("Queued notification payload is invalid")
        return cls(
            title=str(data["title"]),
            sender=str(data["sender"]),
            subject=str(data["subject"]),
            priority_label=str(data["priority_label"]),
            priority_score=int(data["priority_score"]),
            reason=str(data["reason"]),
            summary=str(data.get("summary", "")),
        )


class NotificationBuilder:

    @staticmethod
    def build(message: EmailMessage) -> NotificationPayload:
        """Build a privacy-bounded payload without including the full email body."""
        return NotificationPayload(
            title="High-priority email",
            sender=_short_text(message.sender or "Unknown sender", 120),
            subject=_short_text(message.subject or "(No subject)", 300),
            priority_label=message.priority_label,
            priority_score=message.priority_score,
            reason=_short_text(message.priority_reason or "Important email", 300),
            summary=_short_text(message.body_preview or "", 180),
        )


def _short_text(value: str, maximum_length: int) -> str:
    return " ".join(value.split())[:maximum_length]
