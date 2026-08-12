"""LINE webhook: signature gate, whitelist gate, command routing.

The webhook URL is public, so these tests pin the two security properties:
requests without a valid HMAC signature never reach command handling, and
non-whitelisted senders can only ever learn their own user id.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers import line_webhook

SECRET = "test-channel-secret"
ADMIN_ID = "U0000000000000000000000000000admin"
STRANGER_ID = "U000000000000000000000000stranger"


def _sign(body: bytes, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _event_body(text: str, user_id: str) -> bytes:
    return json.dumps({
        "events": [{
            "type": "message",
            "replyToken": "reply-token-1",
            "source": {"type": "user", "userId": user_id},
            "message": {"type": "text", "text": text},
        }]
    }).encode()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", SECRET)
    monkeypatch.setenv("LINE_ADMIN_USER_IDS", ADMIN_ID)
    return TestClient(app)


@pytest.fixture()
def sent(monkeypatch):
    """Capture outgoing replies/pushes instead of hitting the LINE API."""
    calls = {"replies": [], "pushes": []}

    def fake_reply(token, message):
        calls["replies"].append((token, message))
        return True, ""

    def fake_push(to_id, message):
        calls["pushes"].append((to_id, message))
        return True, ""

    import src.notification.line_service as line_service

    monkeypatch.setattr(line_service, "send_line_reply_message", fake_reply)
    monkeypatch.setattr(line_service, "send_line_push_message", fake_push)
    return calls


def test_signature_verification_roundtrip():
    body = b'{"events": []}'
    assert line_webhook.verify_line_signature(body, _sign(body), SECRET)
    assert not line_webhook.verify_line_signature(body, _sign(body), "other-secret")
    assert not line_webhook.verify_line_signature(body, "garbage", SECRET)
    assert not line_webhook.verify_line_signature(body, "", SECRET)
    assert not line_webhook.verify_line_signature(body, _sign(body), "")


def test_missing_secret_is_service_unavailable(monkeypatch, sent):
    monkeypatch.delenv("LINE_CHANNEL_SECRET", raising=False)
    client = TestClient(app)
    r = client.post("/api/line/webhook", content=b"{}",
                    headers={"X-Line-Signature": "x"})
    assert r.status_code == 503


def test_bad_signature_is_rejected(client, sent):
    body = _event_body("戰報", ADMIN_ID)
    r = client.post("/api/line/webhook", content=body,
                    headers={"X-Line-Signature": "not-a-signature"})
    assert r.status_code == 403
    assert not sent["replies"] and not sent["pushes"]


def test_stranger_gets_own_user_id_only(client, sent):
    body = _event_body("戰報", STRANGER_ID)
    r = client.post("/api/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 200
    assert len(sent["replies"]) == 1
    _, message = sent["replies"][0]
    # The stranger learns their id and nothing about the league.
    assert STRANGER_ID in message
    assert "戰報" not in message.splitlines()[0]
    assert not sent["pushes"]


def test_admin_unknown_command_gets_help(client, sent):
    body = _event_body("哈囉", ADMIN_ID)
    r = client.post("/api/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 200
    assert len(sent["replies"]) == 1
    _, message = sent["replies"][0]
    assert "可用指令" in message


def test_admin_command_routes_to_report(client, sent, monkeypatch):
    import src.notification.scheduler as scheduler

    monkeypatch.setattr(
        scheduler,
        "_weekly_war_report_job",
        lambda dry_run=False, target_id="": {
            "success": True, "report": "WEEKLY-REPORT-TEXT",
        },
    )
    body = _event_body("戰報", ADMIN_ID)
    r = client.post("/api/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 200
    assert len(sent["replies"]) == 1
    _, message = sent["replies"][0]
    assert message == "WEEKLY-REPORT-TEXT"


def test_reply_failure_falls_back_to_push_for_admin(client, monkeypatch):
    calls = {"pushes": []}

    import src.notification.line_service as line_service
    import src.notification.scheduler as scheduler

    monkeypatch.setattr(
        line_service, "send_line_reply_message",
        lambda token, message: (False, "reply token expired"),
    )
    monkeypatch.setattr(
        line_service, "send_line_push_message",
        lambda to_id, message: (calls["pushes"].append((to_id, message)) or (True, "")),
    )
    monkeypatch.setattr(
        scheduler, "_weekly_war_report_job",
        lambda dry_run=False, target_id="": {"success": True, "report": "SLOW-REPORT"},
    )

    body = _event_body("戰報", ADMIN_ID)
    r = client.post("/api/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 200
    assert calls["pushes"] == [(ADMIN_ID, "SLOW-REPORT")]


def test_non_message_events_are_ignored(client, sent):
    body = json.dumps({"events": [{"type": "follow", "replyToken": "t"}]}).encode()
    r = client.post("/api/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 200
    assert not sent["replies"] and not sent["pushes"]
