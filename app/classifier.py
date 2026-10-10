"""Lead classification behind an interface: Claude when configured, deterministic rules otherwise."""
import json
import logging
import re
from typing import Protocol

import httpx

from .models import Classification, EnrichedLead

logger = logging.getLogger("classifier")


class Classifier(Protocol):
    async def classify(self, lead: EnrichedLead) -> Classification: ...


URGENT = re.compile(r"\b(urgent|asap|this week|next week|budget approved|ready to (buy|start))\b", re.I)


class RuleClassifier:
    """Deterministic fallback. Runs offline; used in tests and whenever the LLM is unavailable."""

    async def classify(self, lead: EnrichedLead) -> Classification:
        budget = lead.budget or 0
        urgent = bool(URGENT.search(lead.message))
        if budget >= 10000 and urgent:
            return Classification(tier="hot", reason="high budget + urgency signal", source="rules")
        if budget >= 2000 or urgent:
            return Classification(tier="warm", reason="budget or urgency signal", source="rules")
        return Classification(tier="cold", reason="no budget or urgency signal", source="rules")


class ClaudeClassifier:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str, timeout: float = 10.0):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    async def classify(self, lead: EnrichedLead) -> Classification:
        prompt = (
            "Classify this inbound sales lead as hot, warm or cold. "
            'Reply with JSON only: {"tier": "hot|warm|cold", "reason": "<one short sentence>"}.\n\n'
            f"Company size: {lead.company_size}\nBudget (USD): {lead.budget}\nMessage: {lead.message}"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.URL,
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={"model": self.model, "max_tokens": 150, "messages": [{"role": "user", "content": prompt}]},
            )
            resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        # Pydantic rejects any tier outside hot/warm/cold, which triggers the fallback.
        return Classification(tier=data["tier"], reason=str(data.get("reason", ""))[:200], source="llm")


class FallbackClassifier:
    """Try the primary; on any failure (timeout, 5xx, bad JSON) degrade to rules instead of dropping the lead."""

    def __init__(self, primary: Classifier, fallback: Classifier):
        self.primary, self.fallback = primary, fallback

    async def classify(self, lead: EnrichedLead) -> Classification:
        try:
            return await self.primary.classify(lead)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM classification failed, using rules: %r", exc)
            return await self.fallback.classify(lead)


def build_classifier(api_key: str, model: str) -> Classifier:
    if api_key:
        return FallbackClassifier(ClaudeClassifier(api_key, model), RuleClassifier())
    return RuleClassifier()
