from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime, Integer, String
from app.core.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    """The application's owner account, separate from monitored inboxes."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False
    )

    primary_email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )

    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Every application user may securely connect several email accounts.
    monitored_accounts: Mapped[list["MonitoredEmailAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # A user can opt in one WhatsApp number for priority-email delivery.
    whatsapp_contact: Mapped["WhatsAppContact"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin"
    )
