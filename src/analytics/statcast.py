"""Baseball Savant (Statcast) ingestion and rolling-window aggregation.

Design note — why per-day ingestion instead of Savant's leaderboards:

Savant's `leaderboard/custom` endpoint ignores `start_date` / `end_date` /
`month` entirely (verified: all three return identical season-to-date rows), so
it cannot answer "how has this player looked over the last 15 days" — which is
the whole point of a pickup radar. The pitch-level `statcast_search/csv`
endpoint *does* honour dates, so we pull one day at a time (~3.4k rows, ~2.3MB,
~8s), aggregate it to per-player-per-day totals, and store those. Any rolling
window is then a cheap DB query, and a single fetch feeds both the batter and
the pitcher view because every pitch row carries both IDs.

These endpoints are unofficial. Treat every call as best-effort: on failure the
caller must degrade visibly rather than present stale numbers as current.
"""
from __future__ import annotations

import csv
import os
from datetime import date, timedelta
from typing import Any, Iterable, Iterator

import httpx

STATCAST_CSV_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
STATCAST_TIMEOUT_SECONDS = float(os.getenv("STATCAST_TIMEOUT_SECONDS", "180"))

# Savant marks a "barrel" with launch_speed_angle == 6.
BARREL_CODE = "6"
HARD_HIT_MIN_EV = 95.0

_SWING_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "foul_bunt",
    "hit_into_play",
    "missed_bunt",
    "bunt_foul_tip",
}
_WHIFF_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "missed_bunt",
    "swinging_pitchout",
}
_FASTBALL_NAMES = {"4-Seam Fastball", "Sinker", "Cutter"}


def _f(value: Any) -> float | None:
    """Parse a Savant numeric cell, treating blanks as missing."""
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _i(value: Any) -> int:
    parsed = _f(value)
    return int(parsed) if parsed is not None else 0


def normalize_savant_name(name: str) -> str:
    """Savant reports 'Last, First'; return 'First Last'."""
    name = (name or "").strip().strip('"')
    if "," not in name:
        return name
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def _statcast_day_params(game_day: date) -> dict[str, str]:
    return {
        "all": "true",
        "hfGT": "R|",                      # regular season only
        "player_type": "batter",
        "game_date_gt": game_day.isoformat(),
        "game_date_lt": game_day.isoformat(),
        "type": "details",
    }


def parse_csv_header(header_line: str) -> list[str]:
    """Parse the CSV header, stripping the UTF-8 BOM Savant prefixes it with.

    Without this the first column arrives as '\\ufeff"pitch_type"' and every
    lookup of that column silently misses.
    """
    return next(csv.reader([header_line.lstrip("﻿")]))


def iter_statcast_day(game_day: date) -> Iterator[dict]:
    """Stream one day of regular-season pitch-level Statcast rows.

    Yields rather than materializing: a busy day is ~5.4k rows x 119 columns,
    which costs ~58MB as a list but ~6MB streamed. The container is small, so
    the aggregator consumes each row and drops it.
    """
    with httpx.stream(
        "GET",
        STATCAST_CSV_URL,
        params=_statcast_day_params(game_day),
        timeout=STATCAST_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as resp:
        resp.raise_for_status()
        lines = resp.iter_lines()
        try:
            header = next(lines)
        except StopIteration:
            return
        yield from csv.DictReader(lines, fieldnames=parse_csv_header(header))


def fetch_statcast_day(game_day: date) -> list[dict]:
    """Eager variant of iter_statcast_day(), for tests and ad-hoc analysis."""
    return list(iter_statcast_day(game_day))


def _new_batter_row(player_id: int, name: str, game_day: date) -> dict:
    return {
        "game_date": game_day, "player_id": player_id, "role": "batter",
        "player_name": name,
        "pa": 0, "bbe": 0, "barrels": 0, "hard_hits": 0,
        "ev_sum": 0.0, "xwoba_sum": 0.0, "woba_sum": 0.0, "woba_den": 0,
        "strikeouts": 0, "walks": 0,
        "pitches": 0, "swings": 0, "whiffs": 0,
        "velo_sum": 0.0, "velo_count": 0,
    }


def _new_pitcher_row(player_id: int, name: str, game_day: date) -> dict:
    row = _new_batter_row(player_id, name, game_day)
    row["role"] = "pitcher"
    return row


def aggregate_statcast_rows(rows: Iterable[dict], game_day: date) -> list[dict]:
    """Fold pitch-level rows into per-player-per-day totals for both roles."""
    entries, _ = aggregate_statcast_stream(rows, game_day)
    return entries


def aggregate_statcast_stream(
    rows: Iterable[dict], game_day: date
) -> tuple[list[dict], int]:
    """Fold pitch rows into per-player-per-day totals; also return pitch count.

    Batter rows accumulate the batter's own contact quality; pitcher rows
    accumulate what the pitcher allowed, plus his own velocity and whiffs.
    Consumes `rows` lazily so a streamed day never sits in memory as a list.
    """
    agg: dict[tuple[int, str], dict] = {}
    pitch_count = 0

    for row in rows:
        pitch_count += 1
        description = (row.get("description") or "").strip()
        events = (row.get("events") or "").strip()
        launch_speed = _f(row.get("launch_speed"))
        is_barrel = (row.get("launch_speed_angle") or "").strip() == BARREL_CODE
        is_bbe = launch_speed is not None
        is_hard_hit = is_bbe and launch_speed >= HARD_HIT_MIN_EV
        is_swing = description in _SWING_DESCRIPTIONS
        is_whiff = description in _WHIFF_DESCRIPTIONS
        release_speed = _f(row.get("release_speed"))
        is_fastball = (row.get("pitch_name") or "").strip() in _FASTBALL_NAMES
        xwoba = _f(row.get("estimated_woba_using_speedangle"))
        woba_value = _f(row.get("woba_value"))
        woba_den = _i(row.get("woba_denom"))
        name = normalize_savant_name(row.get("player_name", ""))

        batter_id = _i(row.get("batter"))
        pitcher_id = _i(row.get("pitcher"))

        for player_id, role in ((batter_id, "batter"), (pitcher_id, "pitcher")):
            if not player_id:
                continue
            key = (player_id, role)
            entry = agg.get(key)
            if entry is None:
                # Savant's player_name column always names the batter.
                entry = (
                    _new_batter_row(player_id, name, game_day)
                    if role == "batter"
                    else _new_pitcher_row(player_id, "", game_day)
                )
                agg[key] = entry

            entry["pitches"] += 1
            if is_swing:
                entry["swings"] += 1
            if is_whiff:
                entry["whiffs"] += 1
            if is_bbe:
                entry["bbe"] += 1
                entry["ev_sum"] += launch_speed
                if is_barrel:
                    entry["barrels"] += 1
                if is_hard_hit:
                    entry["hard_hits"] += 1
            if events:
                entry["pa"] += 1
                if events == "strikeout":
                    entry["strikeouts"] += 1
                elif events == "walk":
                    entry["walks"] += 1
                if woba_den:
                    entry["woba_den"] += woba_den
                    if woba_value is not None:
                        entry["woba_sum"] += woba_value
                    if xwoba is not None:
                        entry["xwoba_sum"] += xwoba
            # Velocity is a property of the pitcher only.
            if role == "pitcher" and is_fastball and release_speed is not None:
                entry["velo_sum"] += release_speed
                entry["velo_count"] += 1

    return list(agg.values()), pitch_count


def summarize(entry: dict) -> dict:
    """Turn accumulated totals into the rate stats the radar reasons about."""
    bbe = entry.get("bbe", 0) or 0
    pa = entry.get("pa", 0) or 0
    pitches = entry.get("pitches", 0) or 0
    swings = entry.get("swings", 0) or 0
    woba_den = entry.get("woba_den", 0) or 0
    velo_count = entry.get("velo_count", 0) or 0

    def pct(numerator, denominator):
        return round(100.0 * numerator / denominator, 1) if denominator else None

    xwoba = round(entry["xwoba_sum"] / woba_den, 3) if woba_den else None
    woba = round(entry["woba_sum"] / woba_den, 3) if woba_den else None

    return {
        "player_id": entry.get("player_id"),
        "player_name": entry.get("player_name", ""),
        "role": entry.get("role"),
        "pa": pa,
        "bbe": bbe,
        "pitches": pitches,
        "barrel_rate": pct(entry.get("barrels", 0), bbe),
        "hard_hit_rate": pct(entry.get("hard_hits", 0), bbe),
        "avg_ev": round(entry["ev_sum"] / bbe, 1) if bbe else None,
        "whiff_rate": pct(entry.get("whiffs", 0), swings),
        "k_rate": pct(entry.get("strikeouts", 0), pa),
        "bb_rate": pct(entry.get("walks", 0), pa),
        "xwoba": xwoba,
        "woba": woba,
        # Positive means the player has out-hit his contact quality (regression
        # risk); negative means he has been unlucky (a buy signal).
        "woba_minus_xwoba": (
            round(woba - xwoba, 3) if (woba is not None and xwoba is not None) else None
        ),
        "avg_fastball_velo": (
            round(entry["velo_sum"] / velo_count, 1) if velo_count else None
        ),
    }


MLB_PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"
_NAME_CACHE: dict[int, str] = {}


def resolve_player_names(player_ids: Iterable[int]) -> dict[int, str]:
    """Look up MLB full names by ID (batched, cached, best-effort).

    Needed because Savant's `player_name` column always names the batter, so
    pitcher aggregates would otherwise be nameless.
    """
    wanted = [pid for pid in set(player_ids) if pid and pid not in _NAME_CACHE]
    for chunk_start in range(0, len(wanted), 100):
        chunk = wanted[chunk_start:chunk_start + 100]
        try:
            resp = httpx.get(
                MLB_PEOPLE_URL,
                params={
                    "personIds": ",".join(str(p) for p in chunk),
                    "fields": "people,id,fullName",
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            for person in resp.json().get("people", []):
                pid = person.get("id")
                if pid:
                    _NAME_CACHE[int(pid)] = person.get("fullName", "")
        except Exception as e:
            print(f"[Statcast] Name lookup failed for {len(chunk)} ids: {e}", flush=True)

    return {pid: _NAME_CACHE.get(pid, "") for pid in player_ids if pid}


def sync_statcast_day(game_day: date) -> dict:
    """Fetch, aggregate and persist one day. Returns a small summary dict."""
    from api.database import save_statcast_daily

    entries, pitch_count = aggregate_statcast_stream(
        iter_statcast_day(game_day), game_day
    )
    if not entries:
        return {"date": game_day.isoformat(), "pitches": pitch_count, "players": 0}

    missing = [e["player_id"] for e in entries if not e.get("player_name")]
    if missing:
        names = resolve_player_names(missing)
        for entry in entries:
            if not entry.get("player_name"):
                entry["player_name"] = names.get(entry["player_id"], "")

    save_statcast_daily(game_day, entries)
    return {
        "date": game_day.isoformat(),
        "pitches": pitch_count,
        "players": len(entries),
        "named": sum(1 for e in entries if e.get("player_name")),
    }


def backfill_statcast(start: date, end: date, max_days: int = 30) -> list[dict]:
    """Sync a date range, oldest first, skipping days already stored."""
    from api.database import get_statcast_synced_dates

    already = set(get_statcast_synced_dates(start, end))
    results: list[dict] = []
    day = start
    while day <= end and len(results) < max_days:
        if day not in already:
            try:
                results.append(sync_statcast_day(day))
            except Exception as e:
                print(f"[Statcast] {day} sync failed: {e}", flush=True)
                results.append({"date": day.isoformat(), "error": str(e)})
        day += timedelta(days=1)
    return results
