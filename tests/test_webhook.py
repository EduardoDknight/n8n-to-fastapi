import pytest

from app.classifier import FallbackClassifier, RuleClassifier
from app.sinks import StubSink
from tests.conftest import DownLLM, FlakySink, post


def test_health(make_client):
    client, _ = make_client()
    assert client.get("/health").json()["status"] == "ok"


def test_valid_hot_lead_routes_to_slack_and_crm(make_client, lead):
    sink = StubSink()
    client, _ = make_client(sink=sink)
    r = post(client, lead, key="k1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "hot" and body["routed_to"] == ["slack", "crm"] and body["duplicate"] is False
    assert [d for d, _ in sink.sent] == ["slack", "crm"]


@pytest.mark.parametrize("budget,message,tier,dest", [
    (500, "just browsing", "cold", ["sheet"]),
    (5000, "curious about pricing", "warm", ["crm"]),
])
def test_rule_tiers_and_routing(make_client, lead, budget, message, tier, dest):
    client, _ = make_client()
    body = post(client, {**lead, "budget": budget, "message": message}).json()
    assert body["tier"] == tier and body["routed_to"] == dest


def test_bad_signature_401(make_client, lead):
    sink = StubSink()
    client, _ = make_client(sink=sink)
    assert post(client, lead, secret="wrong-secret").status_code == 401
    assert post(client, lead, signature="").status_code == 401
    assert sink.sent == []


def test_invalid_payload_422(make_client, lead):
    client, _ = make_client()
    assert post(client, {**lead, "email": "not-an-email"}).status_code == 422


def test_duplicate_is_idempotent(make_client, lead):
    sink = StubSink()
    client, _ = make_client(sink=sink)
    first = post(client, lead, key="dup-1").json()
    second = post(client, lead, key="dup-1").json()
    assert second["duplicate"] is True and second["lead_id"] == first["lead_id"]
    assert len(sink.sent) == 2  # slack + crm once, not twice


def test_duplicate_without_key_dedupes_on_body_hash(make_client, lead):
    sink = StubSink()
    client, _ = make_client(sink=sink)
    post(client, lead)
    assert post(client, lead).json()["duplicate"] is True
    assert len(sink.sent) == 2


def test_llm_down_falls_back_to_rules(make_client, lead):
    client, _ = make_client(classifier=FallbackClassifier(DownLLM(), RuleClassifier()))
    r = post(client, lead)
    assert r.status_code == 200
    assert r.json()["classifier"] == "rules" and r.json()["tier"] == "hot"


def test_sink_retry_recovers(make_client, lead):
    sink = FlakySink(failures=2)
    client, app = make_client(sink=sink)
    r = post(client, lead, key="retry-1")
    assert r.status_code == 200
    assert sink.calls == 4  # 2 failures + slack ok + crm ok
    assert app.state.store.audit_events("retry-1") == ["sent:slack", "sent:crm"]


def test_sink_exhausted_returns_502_and_key_is_retryable(make_client, lead):
    sink = FlakySink(failures=3)  # all 3 attempts fail
    client, _ = make_client(sink=sink)
    assert post(client, lead, key="retry-2").status_code == 502
    r = post(client, lead, key="retry-2")  # sender retries once the sink is healthy
    assert r.status_code == 200 and r.json()["duplicate"] is False
