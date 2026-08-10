"""Regression tests for per-season Yahoo league key resolution.

The old hardcoded map resolved unknown seasons to "TBD.l.TBD", so every
Yahoo-dependent job died silently the moment a new season started. These tests
pin the guard and the auto-discovery fallback.
"""
from __future__ import annotations

import pytest

import api.yahoo_service as yahoo_service
from config.settings import get_league_key


# --- static config guard --------------------------------------------------

def test_known_season_resolves_statically():
    assert get_league_key(2026) == "469.l.80910"


@pytest.mark.parametrize("year", [2027, 2030, 1999])
def test_unknown_season_returns_none_not_a_placeholder_key(year):
    assert get_league_key(year) is None


# --- discovery ------------------------------------------------------------

def _yahoo_games_payload(entries):
    """Build a payload shaped like Yahoo's games+leagues collection."""
    games = {"count": len(entries)}
    for idx, (season, leagues) in enumerate(entries):
        games[str(idx)] = {
            "game": [
                {"game_key": str(season), "code": "mlb", "season": str(season)},
                {
                    "leagues": {
                        str(i): {"league": [{"league_key": key, "name": name}]}
                        for i, (key, name) in enumerate(leagues)
                    }
                    | {"count": len(leagues)},
                },
            ]
        }
    return {"fantasy_content": {"users": {"0": {"user": [{"guid": "X"}, {"games": games}]}}}}


def test_discovery_reads_season_from_yahoo_not_a_hardcoded_map(monkeypatch):
    payload = _yahoo_games_payload([
        (2026, [("469.l.80910", "5-Man Keep盟")]),
        (2027, [("481.l.22222", "5-Man Keep盟")]),
    ])
    monkeypatch.setattr(yahoo_service, "yahoo_api_get", lambda path: payload)

    assert yahoo_service.discover_league_keys() == {
        2026: "469.l.80910",
        2027: "481.l.22222",
    }


def test_discovery_ignores_unrelated_leagues(monkeypatch):
    payload = _yahoo_games_payload([
        (2027, [
            ("481.l.11111", "Random Public League"),
            ("481.l.22222", "5-Man Keep盟"),
        ]),
    ])
    monkeypatch.setattr(yahoo_service, "yahoo_api_get", lambda path: payload)

    assert yahoo_service.discover_league_keys() == {2027: "481.l.22222"}


# --- resolution order -----------------------------------------------------

def test_resolution_prefers_static_config_and_skips_discovery(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("discovery must not run when config already knows the key")

    monkeypatch.setattr(yahoo_service, "discover_league_keys", _boom)
    assert yahoo_service.resolve_league_key(2026) == "469.l.80910"


def test_resolution_uses_db_cache_before_discovery(monkeypatch):
    import api.database as db

    monkeypatch.setattr(db, "get_cached_league_key", lambda year: "481.l.22222")
    monkeypatch.setattr(
        yahoo_service,
        "discover_league_keys",
        lambda: (_ for _ in ()).throw(AssertionError("cache should have answered")),
    )
    assert yahoo_service.resolve_league_key(2027) == "481.l.22222"


def test_resolution_discovers_and_caches_a_new_season(monkeypatch):
    import api.database as db

    saved: dict[int, str] = {}
    monkeypatch.setattr(db, "get_cached_league_key", lambda year: None)
    monkeypatch.setattr(
        db, "save_league_key",
        lambda year, key, source="discovered": saved.__setitem__(year, key),
    )
    monkeypatch.setattr(
        yahoo_service, "discover_league_keys", lambda: {2027: "481.l.22222"}
    )

    assert yahoo_service.resolve_league_key(2027) == "481.l.22222"
    assert saved == {2027: "481.l.22222"}, "discovered key must be cached"


def test_resolution_returns_none_when_discovery_fails(monkeypatch):
    import api.database as db

    monkeypatch.setattr(db, "get_cached_league_key", lambda year: None)
    monkeypatch.setattr(
        yahoo_service,
        "discover_league_keys",
        lambda: (_ for _ in ()).throw(RuntimeError("Yahoo down")),
    )
    assert yahoo_service.resolve_league_key(2027) is None
