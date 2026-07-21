"""Request and response schemas for WhatsApp contact and alert delivery."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.phone_number import normalize_e164_phone_number


class WhatsAppContactRequest(BaseModel):
    """A user's explicit consent to receive alerts at an E.164 phone number."""

    phone_number: str = Field(examples=["+14155552671"])
    opt_in: bool

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        """Accept only normalized E.164 numbers that Cloud API can address."""
        return normalize_e164_phone_number(value)

    @field_validator("opt_in")
    @classmethod
    def require_opt_in(cls, value: bool) -> bool:
        """Prevent accidental registration of a number without user consent."""
        if not value:
            raise ValueError("opt_in must be true before WhatsApp alerts can be enabled")
        return value


class WhatsAppContactResponse(BaseModel):
    """Safe delivery-contact details returned to the signed-in user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    phone_number: str
    is_opted_in: bool
    last_inbound_at: datetime | None
    created_at: datetime


class WhatsAppDispatchResponse(BaseModel):
    """The result of trying to send the user's queued priority alerts."""

    queued_count: int
    sent_count: int
    failed_count: int
