"""Shared E.164 phone-number normalization for user and WhatsApp inputs."""

import re


def normalize_e164_phone_number(value: str) -> str:
    """Return a compact E.164 number or reject values that cannot reach WhatsApp."""
    phone_number = value.strip().replace(" ", "")
    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone_number):
        raise ValueError("phone_number must use E.164 format, for example +14155552671")
    return phone_number
