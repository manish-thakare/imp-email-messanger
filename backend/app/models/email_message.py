"""Database model for a message fetched from a monitored inbox."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EmailMessage(Base):
    """A normalized provider message with its latest priority assessment."""

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "provider_message_id", name="uq_account_provider_message"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("monitored_email_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    provider_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    provider_thread_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subject: Mapped[str] = mapped_column(String(1024), default="(No subject)", nullable=False)
    sender: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recipients: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    priority_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    priority_label: Mapped[str] = mapped_column(String(20), default="low", nullable=False, index=True)
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    priority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_source: Mapped[str] = mapped_column(String(30), default="rules", nullable=False)
    # Identifies the normalized content and classifier version used for this assessment.
    classification_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # The message remains scoped to its source inbox for authorization checks.
    account: Mapped["MonitoredEmailAccount"] = relationship(back_populates="messages")
