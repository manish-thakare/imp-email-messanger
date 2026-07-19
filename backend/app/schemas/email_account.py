"""Request and response shapes for connected email accounts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


EmailProvider = Literal["gmail", "outlook"]


class OAuthStartResponse(BaseModel):
    """A provider consent URL the client should open for the user."""

    provider: EmailProvider
    authorization_url: str


class MonitoredEmailAccountResponse(BaseModel):
    """Safe account information that never exposes provider credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: EmailProvider
    email_address: EmailStr
    status: str
    last_synced_at: datetime | None
    error_message: str | None
    created_at: datetime


class SyncResultResponse(BaseModel):
    """Counts returned after an inbox is fetched and classified."""

    account_id: int
    fetched_count: int
    created_count: int
    updated_count: int
    priority_count: int
