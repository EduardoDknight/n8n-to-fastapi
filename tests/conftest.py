import json

import pytest
from fastapi.testclient import TestClient

from app.classifier import RuleClassifier
from app.config import Settings
from app.main import create_app
from app.security import sign
from app.sinks import StubSink

SECRET = "test-secret"


class FlakySink(StubSink):
    """Fails the first `failures` calls, then succeeds."""

    def __init__(self, failures: int):
        super().__init__()
        self.failures, self.calls = failures, 0

    async def send(self, destination, lead, c):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("sink unavailable")
        await super().send(destination, lead, c)


class DownLLM:
    async def classify(self, lead):
        raise TimeoutError("LLM timed out")


@pytest.fixture
def make_client(tmp_path):
    def _make(classifier=None, sink=None):
        settings = Settings(webhook_secret=SECRET, anthropic_api_key="", db_path=str(tmp_path / "t.db"),
                            sinks=("stub",))
        app = create_app(settings, classifier=classifier or RuleClassifier(), sink=sink or StubSink(),
                         retry_base_delay=0)
        return TestClient(app), app

    return _make


@pytest.fixture
def lead():
    return {"name": "Jane Sample", "email": "jane@acme-example.com", "company": "Acme Example Co",
            "budget": 25000, "message": "Budget approved, this is urgent."}


def post(client, payload, key=None, secret=SECRET, signature=None):
    body = json.dumps(payload).encode()
    headers = {"X-Signature": signature if signature is not None else f"sha256={sign(body, secret)}",
               "Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    return client.post("/webhook/lead", content=body, headers=headers)
