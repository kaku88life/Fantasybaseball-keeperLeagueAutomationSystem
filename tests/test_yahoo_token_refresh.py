"""Guards for the serialized Yahoo token refresh.

Why this is worth a test: Yahoo rotates the refresh_token on every refresh.
Before the refresh lock, a scheduler job and a web request could refresh
concurrently; the loser overwrote the DB with a stale refresh_token, and every
later refresh failed with invalid_grant until the commissioner logged in again.
That exact failure mode killed all Yahoo jobs silently from 2026-07-27 to
2026-08-18.
"""
from __future__ import annotations

import datetime
import threading

import pytest

from api import yahoo_service


def _token_row(access="old-access", refresh="refresh-1", expires_in=3600):
    return {
        "user_id": 1,
        "access_token": access,
        "refresh_token": refresh,
        "yahoo_guid": "GUID",
        "expires_at": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=expires_in),
    }


def test_refresh_reuses_token_refreshed_by_another_thread(monkeypatch):
    """If the DB already holds a newer unexpired token when we get the lock,
    return it instead of refreshing again (which would rotate the refresh_token
    a second time for nothing)."""
    fresh = _token_row(access="new-access", refresh="refresh-2")
    monkeypatch.setattr(
        "api.database.get_commissioner_yahoo_token", lambda: fresh
    )

    def _fail_post(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("HTTP refresh must not fire when DB token is fresh")

    monkeypatch.setattr(yahoo_service.requests, "post", _fail_post)

    # Caller still holds the OLD row — simulates losing the race.
    got = yahoo_service.refresh_db_token(_token_row(access="old-access"))
    assert got == "new-access"


def test_refresh_performs_http_call_when_db_token_unchanged(monkeypatch):
    """Normal path: DB row matches the caller's row, so we really refresh."""
    stale = _token_row(access="old-access", refresh="refresh-1", expires_in=-10)
    monkeypatch.setattr(
        "api.database.get_commissioner_yahoo_token", lambda: stale
    )

    saved = {}

    def _fake_upsert(**kwargs):
        saved.update(kwargs)

    monkeypatch.setattr("api.database.upsert_yahoo_token", _fake_upsert)
    monkeypatch.setenv("YAHOO_CLIENT_ID", "cid")
    monkeypatch.setenv("YAHOO_CLIENT_SECRET", "cs")

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "access_token": "brand-new",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
            }

    monkeypatch.setattr(yahoo_service.requests, "post", lambda *a, **k: _Resp())

    got = yahoo_service.refresh_db_token(dict(stale))
    assert got == "brand-new"
    assert saved["refresh_token"] == "refresh-2"


def test_concurrent_refreshes_only_hit_yahoo_once(monkeypatch):
    """Two threads racing to refresh must produce exactly one HTTP call."""
    row = _token_row(access="old-access", refresh="refresh-1", expires_in=-10)
    db = {"row": dict(row)}

    monkeypatch.setattr(
        "api.database.get_commissioner_yahoo_token", lambda: dict(db["row"])
    )

    def _fake_upsert(**kwargs):
        db["row"] = {
            "user_id": kwargs["user_id"],
            "access_token": kwargs["access_token"],
            "refresh_token": kwargs["refresh_token"],
            "yahoo_guid": kwargs.get("yahoo_guid", ""),
            "expires_at": kwargs["expires_at"],
        }

    monkeypatch.setattr("api.database.upsert_yahoo_token", _fake_upsert)
    monkeypatch.setenv("YAHOO_CLIENT_ID", "cid")
    monkeypatch.setenv("YAHOO_CLIENT_SECRET", "cs")

    calls = []
    lock = threading.Lock()

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "access_token": "brand-new",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
            }

    def _fake_post(*args, **kwargs):
        with lock:
            calls.append(1)
        return _Resp()

    monkeypatch.setattr(yahoo_service.requests, "post", _fake_post)

    results = []

    def _worker():
        results.append(yahoo_service.refresh_db_token(dict(row)))

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1, "second thread must reuse the first thread's token"
    assert results == ["brand-new", "brand-new"]
