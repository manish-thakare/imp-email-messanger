"""Database model for a user's opted-in WhatsApp delivery number."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WhatsAppContact(Base):
    """One verified delivery number that belongs to one application user."""

    __tablename__ = "whatsapp_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    is_opted_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # The contact belongs to exactly one signed-in application user.
    user: Mapped["User"] = relationship(back_populates="whatsapp_contact")
