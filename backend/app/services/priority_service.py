"""Assign an importance score to every fetched email message."""

import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logger import logger


@dataclass(frozen=True)
class PriorityAssessment:
    """The classification stored alongside a fetched email."""

    score: int
    label: str
    is_priority: bool
    reason: str
    source: str

    def as_storage_dict(self) -> dict[str, object]:
        """Convert the assessment to model fields used by the message repository."""
        return {
            "priority_score": self.score,
            "priority_label": self.label,
            "is_priority": self.is_priority,
            "priority_reason": self.reason,
            "classification_source": self.source,
        }


class EmailPriorityService:
    """Classify email with an optional deployed model and a dependable rule fallback."""

    async def classify(self, subject: str, sender: str | None, body_preview: str | None) -> PriorityAssessment:
        """Return the best available priority assessment for one normalized message."""
        if settings.LLM_PRIORITY_ENABLED and settings.LLM_PRIORITY_API_URL:
            try:
                return await self._classify_with_llm(subject, sender, body_preview)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("Priority model failed; using rules instead: %s", exc)
        return self._classify_with_rules(subject, sender, body_preview)

    async def _classify_with_llm(
        self, subject: str, sender: str | None, body_preview: str | None
    ) -> PriorityAssessment:
        """Ask an OpenAI-compatible deployed model for a compact JSON assessment."""
        headers = {"Content-Type": "application/json"}
        if settings.LLM_PRIORITY_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_PRIORITY_API_KEY}"

        prompt = (
            "Classify this email for an inbox triage product. Return JSON only with "
            "score (0-100 integer), label (high, medium, or low), and reason (max 160 chars). "
            "High means the user should see it promptly. Consider deadlines, security, money, "
            "work incidents, appointments, and requests requiring action.\n\n"
            f"Subject: {subject}\n"
            f"Sender: {sender or 'unknown'}\n"
            f"Body: {(body_preview or '')[:6000]}"
        )
        payload = {
            "model": settings.LLM_PRIORITY_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a precise email priority classifier."},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.LLM_PRIORITY_API_URL, headers=headers, json=payload)
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(_strip_code_fence(content))
        score = max(0, min(100, int(result["score"])))
        label = str(result["label"]).lower()
        if label not in {"high", "medium", "low"}:
            label = _label_for_score(score)
        return PriorityAssessment(
            score=score,
            label=label,
            is_priority=score >= 70,
            reason=str(result.get("reason", "Classified by deployed model"))[:160],
            source="llm",
        )

    def _classify_with_rules(
        self, subject: str, sender: str | None, body_preview: str | None
    ) -> PriorityAssessment:
        """Score the email locally using transparent urgency and noise indicators."""
        text = " ".join((subject or "", sender or "", body_preview or "")).lower()
        urgent_terms = [
            "urgent", "immediate action", "action required", "deadline", "overdue",
            "security alert", "suspicious", "password", "verify your", "fraud",
            "payment due", "invoice", "interview", "job offer", "production incident",
            "outage", "approval needed", "meeting today", "appointment",
        ]
        action_terms = ["please review", "please respond", "reply requested", "confirm", "sign", "due today"]
        noise_terms = ["newsletter", "unsubscribe", "weekly digest", "promotion", "special offer", "marketing"]

        urgent_matches = _matching_terms(text, urgent_terms)
        action_matches = _matching_terms(text, action_terms)
        noise_matches = _matching_terms(text, noise_terms)
        # One genuine urgency signal should be visible in the priority feed by itself.
        score = 25 + min(60, len(urgent_matches) * 55) + min(30, len(action_matches) * 25)
        score -= min(50, len(noise_matches) * 30)
        score = max(0, min(100, score))
        label = _label_for_score(score)

        if urgent_matches:
            reason = f"Important signals: {', '.join(urgent_matches[:3])}"
        elif action_matches:
            reason = f"Action requested: {', '.join(action_matches[:3])}"
        elif noise_matches:
            reason = f"Low-priority signals: {', '.join(noise_matches[:3])}"
        else:
            reason = "No clear urgent or low-priority signals found"
        return PriorityAssessment(score, label, score >= 70, reason, "rules")


def _matching_terms(text: str, terms: list[str]) -> list[str]:
    """Return each configured term that appears in the normalized email text."""
    return [term for term in terms if term in text]


def _label_for_score(score: int) -> str:
    """Map a numeric score to the label shown in the client inbox."""
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _strip_code_fence(value: str) -> str:
    """Accept JSON returned inside a Markdown code fence by some deployed models."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
