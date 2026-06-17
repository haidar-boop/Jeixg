"""Tests for the two-way SMS approval workflow."""
import pytest

from quanttrade.notifications.approvals import (
    APPROVED,
    DENIED,
    PENDING,
    ApprovalStore,
    parse_reply,
)


@pytest.mark.parametrize("text,decision,symbol", [
    ("yes", True, None),
    ("YES", True, None),
    ("y aapl", True, "AAPL"),
    ("buy NVDA", True, "NVDA"),
    ("no", False, None),
    ("skip tsla", False, "TSLA"),
    ("maybe", None, None),
    ("", None, None),
])
def test_parse_reply(text, decision, symbol):
    assert parse_reply(text) == (decision, symbol)


@pytest.fixture
def store(tmp_path):
    return ApprovalStore(tmp_path / "approvals.json")


def test_create_and_outstanding(store):
    assert not store.has_outstanding()
    store.create_request("AAPL", 100.0, "RSI oversold", stop_loss=95.0)
    assert store.has_outstanding()


def test_approve_then_execute(store):
    store.create_request("AAPL", 100.0, "dip")
    req = store.record_decision(True, None)
    assert req["symbol"] == "AAPL" and req["status"] == APPROVED
    assert [r["symbol"] for r in store.pop_approved()] == ["AAPL"]
    store.mark_executed("AAPL")
    assert not store.has_outstanding()
    assert store.pop_approved() == []


def test_deny(store):
    store.create_request("TSLA", 200.0, "dip")
    req = store.record_decision(False, None)
    assert req["status"] == DENIED
    assert not store.has_outstanding()


def test_decision_without_pending(store):
    assert store.record_decision(True, None) is None


def test_cooldown_blocks_reask(store):
    store.create_request("AAPL", 100.0, "dip")
    store.record_decision(False, "AAPL")
    assert store.in_cooldown("AAPL", cooldown_seconds=3600)
    assert not store.in_cooldown("MSFT", cooldown_seconds=3600)


def test_expire(store):
    store.create_request("AAPL", 100.0, "dip")
    assert store.expire_old(ttl_seconds=-1) == 1   # already past TTL
    assert not store.has_outstanding()


def test_pending_blocks_reask(store):
    store.create_request("AAPL", 100.0, "dip")
    assert store.in_cooldown("AAPL")  # pending counts as in-cooldown


def test_sms_webhook(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_APPROVALS_PATH", str(tmp_path / "approvals.json"))
    monkeypatch.setenv("QT_TWILIO_TO", "+15551234567")
    ApprovalStore().create_request("AAPL", 100.0, "dip")

    from quanttrade.api.wsgi import create_wsgi_app
    client = create_wsgi_app(service=object()).test_client()

    # Wrong number is ignored.
    bad = client.post("/sms", data={"From": "+19999999999", "Body": "YES"})
    assert b"authorized" in bad.data

    # Correct number approves.
    ok = client.post("/sms", data={"From": "+15551234567", "Body": "YES"})
    assert b"buying AAPL" in ok.data
    assert [r["symbol"] for r in ApprovalStore().pop_approved()] == ["AAPL"]
