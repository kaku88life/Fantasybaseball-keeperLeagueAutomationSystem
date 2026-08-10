"""Regression tests for war-report stat windows and missed-run catch-up.

These cover the two failures that actually shipped:
1. Weekly/monthly reports displayed SEASON totals under a "本週/本月" heading,
   because Yahoo's `out=stats` ignores `sort_type`.
2. Scheduled reports vanished with no trace when the container was down at the
   trigger time.

Everything here is pure logic — no network, no DB.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.notification import scheduler as s

TZ = ZoneInfo("Asia/Taipei")


# --- date windows ---------------------------------------------------------

def test_month_date_range_handles_month_and_year_edges():
    assert s._month_date_range(2026, 7) == (date(2026, 7, 1), date(2026, 7, 31))
    assert s._month_date_range(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert s._month_date_range(2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))
    assert s._month_date_range(2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))


def test_split_in_date_range_is_inclusive():
    assert s._split_in_date_range({"date": "2026-07-01"}, date(2026, 7, 1), date(2026, 7, 31))
    assert s._split_in_date_range({"date": "2026-07-31"}, date(2026, 7, 1), date(2026, 7, 31))
    assert not s._split_in_date_range({"date": "2026-08-01"}, date(2026, 7, 1), date(2026, 7, 31))
    assert not s._split_in_date_range({}, date(2026, 7, 1), date(2026, 7, 31))


def test_matchup_week_range_reads_yahoo_week_bounds():
    matchup = {"week": "19", "week_start": "2026-08-03", "week_end": "2026-08-09"}
    assert s._matchup_week_range(matchup) == (date(2026, 8, 3), date(2026, 8, 9))
    assert s._matchup_week_range({}) == (None, None)


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 8, 10), (date(2026, 8, 3), date(2026, 8, 9))),   # Monday
        (date(2026, 8, 9), (date(2026, 7, 27), date(2026, 8, 2))),   # Sunday
        (date(2026, 8, 12), (date(2026, 8, 3), date(2026, 8, 9))),   # midweek
    ],
)
def test_fallback_week_range_returns_last_completed_week(today, expected):
    assert s._fallback_week_range(today) == expected


# --- renderers: a missing window must never look like real output ---------

def test_batter_block_marks_missing_window_instead_of_showing_stale_numbers():
    players = [{
        "name": "Ghost Player",
        "position": "1B",
        "owner_team": "FA",
        "stats": {},
        "stats_window_ok": False,
    }]
    rendered = "\n".join(s._build_top_batter_lines(players, "本週"))
    assert "本週數據暫缺" in rendered
    assert "AVG" not in rendered


def test_pitcher_block_hides_irrelevant_counting_stats_by_role():
    def render(position, stats):
        return "\n".join(s._build_top_pitcher_lines(
            [{
                "name": "X",
                "position": position,
                "owner_team": "FA",
                "stats": stats,
                "stats_window_ok": True,
            }],
            "本週",
        ))

    sp = render("SP", {"IP": "14.0", "W": "2", "K": "21", "QS": "2",
                       "ERA": "1.29", "WHIP": "0.79", "SV": "0", "HLD": "0"})
    assert "QS" in sp and "SV" not in sp and "HLD" not in sp

    rp = render("RP", {"IP": "4.0", "W": "0", "K": "5", "QS": "0",
                       "ERA": "0.00", "WHIP": "0.50", "SV": "3", "HLD": "1"})
    assert "SV" in rp and "HLD" in rp and "QS" not in rp


def test_footer_separates_ranking_source_from_stat_window():
    footer = "\n".join(s._report_source_lines("Yahoo Fantasy Points（夢幻積分 PTS）", "8/3-8/9"))
    assert "8/3-8/9" in footer
    assert "MLB Stats API" in footer


# --- startup catch-up -----------------------------------------------------

def test_last_weekly_occurrence_brackets_the_monday_trigger():
    # Before Monday 21:00 -> previous week's trigger.
    assert s._last_weekly_occurrence(datetime(2026, 8, 10, 20, 0, tzinfo=TZ)) == \
        datetime(2026, 8, 3, 21, 0, tzinfo=TZ)
    # After it -> today's trigger.
    assert s._last_weekly_occurrence(datetime(2026, 8, 10, 21, 30, tzinfo=TZ)) == \
        datetime(2026, 8, 10, 21, 0, tzinfo=TZ)


def test_last_monthly_occurrence_crosses_the_year_boundary():
    assert s._last_monthly_occurrence(datetime(2026, 1, 1, 10, 0, tzinfo=TZ)) == \
        datetime(2025, 12, 1, 20, 45, tzinfo=TZ)


class _CatchupHarness:
    """Drives _catch_up_job with a stubbed job-run history."""

    def __init__(self, monkeypatch, *, history: bool, last_success):
        import api.database as db

        monkeypatch.setattr(db, "has_job_history", lambda job_id: history)
        monkeypatch.setattr(db, "get_last_job_success", lambda job_id: last_success)
        monkeypatch.setattr(s, "_record_run", lambda *a, **k: None)
        self.calls: list[str] = []

    def run(self, occurrence, now, max_age_hours=48.0):
        return s._catch_up_job(
            "war_report",
            lambda: self.calls.append("fired"),
            occurrence,
            max_age_hours,
            now,
        )


NOW = datetime(2026, 8, 11, 9, 0, tzinfo=TZ)
OCCURRENCE = datetime(2026, 8, 10, 21, 0, tzinfo=TZ)


def test_catchup_fires_when_run_was_missed(monkeypatch):
    h = _CatchupHarness(monkeypatch, history=True, last_success=OCCURRENCE - timedelta(days=7))
    assert h.run(OCCURRENCE, NOW) is True
    assert h.calls == ["fired"]


def test_catchup_skips_when_already_sent(monkeypatch):
    h = _CatchupHarness(monkeypatch, history=True, last_success=OCCURRENCE + timedelta(minutes=2))
    assert h.run(OCCURRENCE, NOW) is False
    assert h.calls == []


def test_catchup_tolerates_naive_timestamps_from_the_db(monkeypatch):
    naive = (OCCURRENCE + timedelta(minutes=2)).replace(tzinfo=None)
    h = _CatchupHarness(monkeypatch, history=True, last_success=naive)
    assert h.run(OCCURRENCE, NOW) is False


def test_catchup_does_not_spam_on_a_fresh_deployment(monkeypatch):
    """No history means no baseline — not a missed run."""
    h = _CatchupHarness(monkeypatch, history=False, last_success=None)
    assert h.run(OCCURRENCE, NOW) is False
    assert h.calls == []


def test_catchup_refuses_to_send_a_stale_report(monkeypatch):
    h = _CatchupHarness(monkeypatch, history=True, last_success=None)
    stale = OCCURRENCE - timedelta(days=5)
    assert h.run(stale, NOW) is False
    assert h.calls == []
