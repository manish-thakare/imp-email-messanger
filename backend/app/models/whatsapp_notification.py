"""Durable delivery outbox for priority-email WhatsApp notifications."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WhatsAppNotification(Base):
    """A single queued or delivered WhatsApp alert for one important email."""

    __tablename__ = "whatsapp_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_message_id: Mapped[int] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    # Snapshot the bounded notification content at queue time.
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # The source message is loaded when building the approved alert template.
    email_message: Mapped["EmailMessage"] = relationship()
