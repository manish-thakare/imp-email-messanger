"""Weighted, explainable signals used by the deterministic first-pass classifier."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PriorityRule:
    """One normalized signal and its contribution to an email's score."""

    key: str
    category: str
    weight: int
    phrases: tuple[str, ...]


# Rules are intentionally plain data so product owners can review and tune them.
PRIORITY_RULES: tuple[PriorityRule, ...] = (
    PriorityRule(
        "security", "security", 60,
        ("security alert", "suspicious", "fraud", "verify your", "password"),
    ),
    PriorityRule(
        "urgent", "urgency", 55,
        ("urgent", "immediate action", "action required", "deadline", "overdue"),
    ),
    PriorityRule(
        "financial", "money", 45,
        ("payment due", "invoice", "receipt", "wire transfer", "tax document"),
    ),
    PriorityRule(
        "work_incident", "work", 50,
        ("production incident", "outage", "service degraded", "approval needed"),
    ),
    PriorityRule(
        "time_sensitive", "time", 35,
        ("meeting today", "appointment", "interview", "job offer", "due today"),
    ),
    PriorityRule(
        "requested_action", "action", 25,
        ("please review", "please respond", "reply requested", "confirm", "sign"),
    ),
    PriorityRule(
        "newsletter", "noise", -30,
        ("newsletter", "unsubscribe", "weekly digest"),
    ),
    PriorityRule(
        "marketing", "noise", -30,
        ("promotion", "special offer", "marketing"),
    ),
)

BASE_PRIORITY_SCORE = 20
PRIORITY_THRESHOLD = 70
