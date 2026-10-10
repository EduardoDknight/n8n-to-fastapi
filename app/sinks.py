"""Outbound destinations as pluggable adapters (Slack, Google Sheets and CRM in the original flow)."""
import logging
from typing import Protocol

from .models import Classification, EnrichedLead

logger = logging.getLogger("sinks")

# Same routing table as the n8n Switch node.
ROUTES: dict[str, list[str]] = {
    "hot": ["slack", "crm"],
    "warm": ["crm"],
    "cold": ["sheet"],
}


class Sink(Protocol):
    async def send(self, destination: str, lead: EnrichedLead, c: Classification) -> None: ...


class ConsoleSink:
    async def send(self, destination: str, lead: EnrichedLead, c: Classification) -> None:
        logger.info("-> %s: lead from %s tier=%s", destination, lead.domain, c.tier)


class StubSink:
    """Records calls in memory. Useful for tests and dry-runs."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, destination: str, lead: EnrichedLead, c: Classification) -> None:
        self.sent.append((destination, lead.email))


def build_sink(names: tuple[str, ...]) -> Sink:
    # Real adapters (Slack incoming webhook, Sheets API, CRM REST) implement the same `send` interface.
    return StubSink() if "stub" in names else ConsoleSink()
