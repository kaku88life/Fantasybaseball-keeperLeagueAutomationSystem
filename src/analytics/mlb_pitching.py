"""Official MLB pitching lines, used for the inputs Statcast cannot give us.

Statcast pitch data has no innings-pitched column, and reconstructing outs from
`outs_when_up` is error-prone (inning changes, double plays, mid-inning pitching
changes). MLB's own `byDateRange` endpoint returns the whole league's pitching
line in a single request, so FIP is computed from official numbers instead of
inferred ones.

Innings are stored as OUTS. MLB reports "2.2" meaning 2⅔ innings — summing that
as a decimal silently corrupts every aggregate.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import httpx

MLB_STATS_URL = "https://statsapi.mlb.com/api/v1/stats"
MLB_PITCHING_TIMEOUT = float(os.getenv("MLB_PITCHING_TIMEOUT_SECONDS", "90"))


def ip_to_outs(value: Any) -> int:
    """Convert MLB's "2.2" (2⅔ innings) notation to outs."""
    text = str(value or "0").strip()
    if not text:
        return 0
    whole, _, frac = text.partition(".")
    try:
        outs = int(whole or 0) * 3
    except ValueError:
        return 0
    if frac:
        try:
            # The fractional digit is thirds of an inning, not a decimal.
            outs += min(int(frac[0]), 2)
        except ValueError:
            pass
    return outs


def outs_to_ip(outs: int) -> str:
    whole, rem = divmod(max(outs, 0), 3)
    return f"{whole}.{rem}"


def _int(stat: dict, *keys: str) -> int:
    for key in keys:
        value = stat.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def fetch_pitching_range(start: date, end: date) -> list[dict]:
    """Fetch every pitcher's official line over [start, end] in one request."""
    resp = httpx.get(
        MLB_STATS_URL,
        params={
            "stats": "byDateRange",
            "group": "pitching",
            "sportId": "1",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "limit": "2000",
            "playerPool": "ALL",
        },
        timeout=MLB_PITCHING_TIMEOUT,
    )
    resp.raise_for_status()

    splits = (resp.json().get("stats") or [{}])[0].get("splits", [])
    rows: list[dict] = []
    for split in splits:
        player = split.get("player") or {}
        player_id = player.get("id")
        if not player_id:
            continue
        stat = split.get("stat") or {}
        rows.append({
            "player_id": int(player_id),
            "player_name": player.get("fullName", ""),
            "ip_outs": ip_to_outs(stat.get("inningsPitched")),
            "hr": _int(stat, "homeRuns"),
            "bb": _int(stat, "baseOnBalls"),
            "hbp": _int(stat, "hitBatsmen", "hitByPitch"),
            "strikeouts": _int(stat, "strikeOuts", "strikeouts"),
            "earned_runs": _int(stat, "earnedRuns"),
            "batters_faced": _int(stat, "battersFaced"),
        })
    return rows


def league_fip_constant(rows: list[dict]) -> float | None:
    """Derive this season's FIP constant from the league's own totals.

    cFIP = lgERA - (13*HR + 3*(BB+HBP) - 2*K) / IP

    Deriving it beats hardcoding ~3.10: the constant drifts year to year, and a
    stale constant shifts every FIP we display.
    """
    outs = sum(r["ip_outs"] for r in rows)
    if outs < 300:  # too little data to calibrate against
        return None
    innings = outs / 3
    lg_era = sum(r["earned_runs"] for r in rows) * 9 / innings
    raw = (
        13 * sum(r["hr"] for r in rows)
        + 3 * (sum(r["bb"] for r in rows) + sum(r["hbp"] for r in rows))
        - 2 * sum(r["strikeouts"] for r in rows)
    ) / innings
    return round(lg_era - raw, 3)


def compute_fip(row: dict, constant: float | None) -> float | None:
    """FIP for one pitcher. None when the sample or the constant is missing."""
    if constant is None:
        return None
    outs = row.get("ip_outs", 0) or 0
    if outs < 9:  # under 3 innings FIP is noise
        return None
    innings = outs / 3
    raw = (
        13 * (row.get("hr", 0) or 0)
        + 3 * ((row.get("bb", 0) or 0) + (row.get("hbp", 0) or 0))
        - 2 * (row.get("strikeouts", 0) or 0)
    ) / innings
    return round(raw + constant, 2)


def summarize_pitching(row: dict, constant: float | None) -> dict:
    """Display-ready official pitching line plus FIP."""
    outs = row.get("ip_outs", 0) or 0
    innings = outs / 3 if outs else 0
    era = round((row.get("earned_runs", 0) or 0) * 9 / innings, 2) if innings else None
    return {
        "player_id": row.get("player_id"),
        "player_name": row.get("player_name", ""),
        "ip": outs_to_ip(outs),
        "ip_outs": outs,
        "hr": row.get("hr", 0),
        "bb": row.get("bb", 0),
        "hbp": row.get("hbp", 0),
        "strikeouts": row.get("strikeouts", 0),
        "era": era,
        "fip": compute_fip(row, constant),
        # Negative means the pitcher has out-performed his peripherals, i.e.
        # ERA is likely to regress upward.
        "era_minus_fip": (
            round(era - compute_fip(row, constant), 2)
            if era is not None and compute_fip(row, constant) is not None
            else None
        ),
    }


def sync_pitching_day(game_day: date) -> dict:
    """Fetch and persist one day of official pitching lines."""
    from api.database import save_mlb_pitching_daily

    rows = fetch_pitching_range(game_day, game_day)
    if not rows:
        return {"date": game_day.isoformat(), "pitchers": 0}
    save_mlb_pitching_daily(game_day, rows)
    return {"date": game_day.isoformat(), "pitchers": len(rows)}


def backfill_pitching(start: date, end: date, max_days: int = 30) -> list[dict]:
    """Sync a date range, skipping days already stored."""
    from api.database import get_mlb_pitching_synced_dates

    already = set(get_mlb_pitching_synced_dates(start, end))
    results: list[dict] = []
    day = start
    while day <= end and len(results) < max_days:
        if day not in already:
            try:
                results.append(sync_pitching_day(day))
            except Exception as e:
                print(f"[MLBPitching] {day} sync failed: {e}", flush=True)
                results.append({"date": day.isoformat(), "error": str(e)})
        day += timedelta(days=1)
    return results
