"""Regression tests for Statcast aggregation and the FA radar scoring.

The aggregation is the foundation of every advanced-stat feature, so the key
invariant is pinned here: batter-side and pitcher-side totals must reconcile,
because both are folded from the same pitch rows.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.analytics import fa_radar
from src.analytics.statcast import (
    aggregate_statcast_rows,
    aggregate_statcast_stream,
    normalize_savant_name,
    parse_csv_header,
    summarize,
)

DAY = date(2025, 7, 1)


def pitch(**kw):
    """One Statcast pitch row with sane defaults."""
    row = {
        "player_name": "Judge, Aaron",
        "batter": "592450",
        "pitcher": "656550",
        "events": "",
        "description": "ball",
        "launch_speed": "",
        "launch_angle": "",
        "launch_speed_angle": "",
        "estimated_woba_using_speedangle": "",
        "woba_value": "",
        "woba_denom": "",
        "release_speed": "95.0",
        "pitch_name": "4-Seam Fastball",
    }
    row.update(kw)
    return row


# --- name handling --------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Judge, Aaron", "Aaron Judge"),
        ("O'Hoppe, Logan", "Logan O'Hoppe"),
        ("Tatis Jr., Fernando", "Fernando Tatis Jr."),
        ("Ohtani", "Ohtani"),
        ("", ""),
    ],
)
def test_savant_names_are_flipped_to_first_last(raw, expected):
    assert normalize_savant_name(raw) == expected


# --- CSV header / BOM -----------------------------------------------------

def test_bom_is_stripped_from_the_first_column_name():
    """Savant prefixes a BOM; leaving it in silently breaks pitch_type lookups."""
    header = '﻿"pitch_type",game_date,release_speed'
    assert parse_csv_header(header) == ["pitch_type", "game_date", "release_speed"]


def test_header_without_bom_is_unchanged():
    assert parse_csv_header("a,b,c") == ["a", "b", "c"]


# --- aggregation ----------------------------------------------------------

def test_streaming_aggregation_reports_pitch_count_without_a_list():
    """sync uses the streaming variant, so it must return the pitch tally itself."""
    def rows():
        yield pitch(description="swinging_strike")
        yield pitch(events="single", description="hit_into_play",
                    launch_speed="99.0", woba_value="0.9", woba_denom="1")

    entries, pitch_count = aggregate_statcast_stream(rows(), DAY)
    assert pitch_count == 2
    assert {e["role"] for e in entries} == {"batter", "pitcher"}



def test_batter_and_pitcher_totals_reconcile():
    """Both roles are folded from the same rows, so their sums must match."""
    rows = [
        pitch(description="swinging_strike"),
        pitch(events="home_run", description="hit_into_play", launch_speed="108.0",
              launch_speed_angle="6", woba_value="2.0", woba_denom="1",
              estimated_woba_using_speedangle="1.8"),
        pitch(batter="111", events="strikeout", description="swinging_strike",
              woba_value="0", woba_denom="1"),
    ]
    entries = aggregate_statcast_rows(rows, DAY)
    batters = [e for e in entries if e["role"] == "batter"]
    pitchers = [e for e in entries if e["role"] == "pitcher"]

    assert sum(e["pa"] for e in batters) == sum(e["pa"] for e in pitchers) == 2
    assert sum(e["pitches"] for e in batters) == sum(e["pitches"] for e in pitchers) == 3


def test_barrel_hard_hit_and_whiff_classification():
    rows = [
        # Barrel (also a hard hit).
        pitch(events="home_run", description="hit_into_play", launch_speed="108.0",
              launch_speed_angle="6", woba_value="2.0", woba_denom="1"),
        # Hard hit but not a barrel.
        pitch(events="single", description="hit_into_play", launch_speed="99.0",
              launch_speed_angle="4", woba_value="0.9", woba_denom="1"),
        # Softly hit.
        pitch(events="field_out", description="hit_into_play", launch_speed="70.0",
              launch_speed_angle="2", woba_value="0", woba_denom="1"),
        # Whiff (no batted ball).
        pitch(description="swinging_strike"),
    ]
    batter = next(
        e for e in aggregate_statcast_rows(rows, DAY) if e["role"] == "batter"
    )
    assert batter["bbe"] == 3
    assert batter["barrels"] == 1
    assert batter["hard_hits"] == 2
    assert batter["whiffs"] == 1
    assert batter["swings"] == 4  # 3 in play + 1 swinging strike

    stats = summarize(batter)
    assert stats["barrel_rate"] == pytest.approx(33.3, abs=0.1)
    assert stats["hard_hit_rate"] == pytest.approx(66.7, abs=0.1)
    assert stats["whiff_rate"] == 25.0


def test_velocity_is_attributed_to_the_pitcher_only():
    rows = [
        pitch(release_speed="97.5", pitch_name="4-Seam Fastball"),
        pitch(release_speed="82.0", pitch_name="Curveball"),  # not a fastball
    ]
    entries = aggregate_statcast_rows(rows, DAY)
    pitcher = next(e for e in entries if e["role"] == "pitcher")
    batter = next(e for e in entries if e["role"] == "batter")

    assert summarize(pitcher)["avg_fastball_velo"] == 97.5  # curveball excluded
    assert summarize(batter)["avg_fastball_velo"] is None


def test_missing_samples_summarize_to_none_not_zero():
    """A missing rate must be unknown, never a misleading 0."""
    stats = summarize(
        {"player_id": 1, "role": "batter", "player_name": "X", "pa": 0, "bbe": 0,
         "pitches": 0, "swings": 0, "woba_den": 0, "barrels": 0, "hard_hits": 0,
         "ev_sum": 0.0, "xwoba_sum": 0.0, "woba_sum": 0.0, "strikeouts": 0,
         "walks": 0, "whiffs": 0, "velo_sum": 0.0, "velo_count": 0}
    )
    assert stats["barrel_rate"] is None
    assert stats["xwoba"] is None
    assert stats["avg_ev"] is None
    assert stats["woba_minus_xwoba"] is None


def test_woba_gap_flags_luck_direction():
    entry = {
        "player_id": 1, "role": "batter", "player_name": "X", "pa": 10, "bbe": 8,
        "pitches": 40, "swings": 20, "woba_den": 10, "barrels": 1, "hard_hits": 4,
        "ev_sum": 720.0, "xwoba_sum": 4.5, "woba_sum": 3.0, "strikeouts": 2,
        "walks": 1, "whiffs": 5, "velo_sum": 0.0, "velo_count": 0,
    }
    stats = summarize(entry)
    assert stats["xwoba"] == 0.45
    assert stats["woba"] == 0.30
    # Under-performing his contact quality -> negative gap -> a buy signal.
    assert stats["woba_minus_xwoba"] == pytest.approx(-0.15)


# --- radar scoring --------------------------------------------------------

def test_batter_scoring_rewards_improvement_over_own_baseline():
    recent = {"barrel_rate": 14.0, "hard_hit_rate": 52.0, "xwoba": 0.400,
              "woba_minus_xwoba": -0.070}
    season = {"barrel_rate": 6.0, "xwoba": 0.320}

    score, reasons = fa_radar._score_batter(recent, season)
    flat_score, _ = fa_radar._score_batter(recent, {"barrel_rate": 14.0, "xwoba": 0.400})

    assert score > flat_score, "a rising profile must outscore a flat one"
    assert any("買點" in r for r in reasons)


def test_pitcher_velocity_drop_is_a_warning_not_a_buy_signal():
    recent = {"whiff_rate": 20.0, "xwoba": 0.340, "avg_fastball_velo": 91.0}
    season = {"whiff_rate": 20.0, "xwoba": 0.340, "avg_fastball_velo": 94.0}

    score, reasons = fa_radar._score_pitcher(recent, season)
    assert score == 0, "a velocity drop must not add score"
    assert any("傷兵風險" in r for r in reasons)


def test_pitcher_scoring_rewards_stuff():
    recent = {"whiff_rate": 35.0, "xwoba": 0.250, "avg_fastball_velo": 96.0}
    score, reasons = fa_radar._score_pitcher(recent, None)
    assert score >= 50
    assert any("whiff" in r for r in reasons)


# --- new metrics: CSW%, chase%, batted-ball mix, xBA/xSLG ------------------

def test_csw_counts_called_strikes_and_whiffs_over_all_pitches():
    rows = [
        pitch(description="called_strike"),
        pitch(description="swinging_strike"),
        pitch(description="ball"),
        pitch(description="foul"),
    ]
    stats = summarize(
        next(e for e in aggregate_statcast_rows(rows, DAY) if e["role"] == "pitcher")
    )
    # 1 called + 1 whiff out of 4 pitches
    assert stats["csw_rate"] == 50.0
    # whiff% uses swings (3: swinging_strike, foul... only 2 are swings here)
    assert stats["whiff_rate"] == 50.0


def test_chase_rate_uses_savant_zone_codes():
    rows = [
        pitch(zone="13", description="swinging_strike"),  # out of zone, swung
        pitch(zone="14", description="ball"),             # out of zone, took
        pitch(zone="5", description="swinging_strike"),   # in zone, swung
    ]
    stats = summarize(
        next(e for e in aggregate_statcast_rows(rows, DAY) if e["role"] == "batter")
    )
    assert stats["chase_rate"] == 50.0  # 1 of 2 out-of-zone pitches


def test_batted_ball_mix_sums_to_100():
    rows = [
        pitch(events="single", description="hit_into_play", bb_type="ground_ball",
              launch_speed="80.0", woba_value="0.9", woba_denom="1"),
        pitch(events="double", description="hit_into_play", bb_type="line_drive",
              launch_speed="99.0", woba_value="1.2", woba_denom="1"),
        pitch(events="field_out", description="hit_into_play", bb_type="fly_ball",
              launch_speed="90.0", woba_value="0", woba_denom="1"),
        pitch(events="field_out", description="hit_into_play", bb_type="popup",
              launch_speed="60.0", woba_value="0", woba_denom="1"),
    ]
    stats = summarize(
        next(e for e in aggregate_statcast_rows(rows, DAY) if e["role"] == "batter")
    )
    assert stats["gb_rate"] == 25.0
    assert stats["ld_rate"] == 25.0
    assert stats["fb_rate"] == 50.0  # fly balls and popups together
    assert stats["gb_rate"] + stats["ld_rate"] + stats["fb_rate"] == 100.0


def test_xba_and_xslg_use_the_woba_denominator():
    rows = [
        pitch(events="home_run", description="hit_into_play", launch_speed="108.0",
              woba_value="2.0", woba_denom="1",
              estimated_ba_using_speedangle="0.9",
              estimated_slg_using_speedangle="3.2"),
        pitch(events="field_out", description="hit_into_play", launch_speed="70.0",
              woba_value="0", woba_denom="1",
              estimated_ba_using_speedangle="0.1",
              estimated_slg_using_speedangle="0.1"),
    ]
    stats = summarize(
        next(e for e in aggregate_statcast_rows(rows, DAY) if e["role"] == "batter")
    )
    assert stats["xba"] == pytest.approx(0.5)
    assert stats["xslg"] == pytest.approx(1.65)
