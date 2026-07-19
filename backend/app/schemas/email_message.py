"""Response shapes for the user's prioritized message feed."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmailMessageResponse(BaseModel):
    """A classified message returned in the application's inbox feed."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    provider_message_id: str
    subject: str
    sender: str | None
    recipients: str | None
    body_preview: str | None
    received_at: datetime | None
    priority_score: int
    priority_label: str
    is_priority: bool
    priority_reason: str | None
    classification_source: str
