"""Import every model so SQLAlchemy can resolve mapped relationships."""

from app.models.email_message import EmailMessage
from app.models.monitored_email_account import MonitoredEmailAccount
from app.models.user import User
from app.models.whatsapp_contact import WhatsAppContact
from app.models.whatsapp_notification import WhatsAppNotification

__all__ = [
    "EmailMessage",
    "MonitoredEmailAccount",
    "User",
    "WhatsAppContact",
    "WhatsAppNotification",
]
