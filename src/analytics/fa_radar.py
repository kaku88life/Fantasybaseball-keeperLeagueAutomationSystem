"""Free-agent radar: surface unowned players whose underlying data is rising.

The signal is deliberately *not* "who put up the best line last week" — that is
already visible in Yahoo. It is "whose contact quality / stuff over a recent
window is better than their season-long profile", which is where unowned value
actually hides.

Every number here comes from statcast_daily (see src.analytics.statcast for why
we ingest per-day). Ownership comes from the same Yahoo roster lookup the war
reports use, so a player rostered by any of the 16 teams is excluded.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from src.analytics.statcast import summarize

# Window defaults. 15 days is long enough for contact-quality rates to mean
# something and short enough to catch a role change.
RECENT_WINDOW_DAYS = 15
# Minimum sample before a player is allowed to appear at all.
MIN_RECENT_PA_BATTER = 20
MIN_RECENT_PITCHES_PITCHER = 100


def _delta(recent: Any, baseline: Any) -> float | None:
    if recent is None or baseline is None:
        return None
    return round(recent - baseline, 3)


def _score_batter(recent: dict, season: dict | None) -> tuple[float, list[str]]:
    """Score a hitter and explain why, in plain terms."""
    score = 0.0
    reasons: list[str] = []

    barrel = recent.get("barrel_rate")
    hard_hit = recent.get("hard_hit_rate")
    xwoba = recent.get("xwoba")
    gap = recent.get("woba_minus_xwoba")

    # Absolute quality — elite contact is worth noticing on its own.
    if barrel is not None and barrel >= 12:
        score += 25
        reasons.append(f"近期 barrel% {barrel}（優異）")
    elif barrel is not None and barrel >= 8:
        score += 12
        reasons.append(f"近期 barrel% {barrel}（偏高）")

    if hard_hit is not None and hard_hit >= 50:
        score += 15
        reasons.append(f"強擊率 {hard_hit}%")

    if xwoba is not None and xwoba >= 0.380:
        score += 25
        reasons.append(f"近期 xwOBA {xwoba:.3f}")
    elif xwoba is not None and xwoba >= 0.340:
        score += 12
        reasons.append(f"近期 xwOBA {xwoba:.3f}")

    # Unlucky = the buy window. Actual output lags contact quality.
    if gap is not None and gap <= -0.060:
        score += 20
        reasons.append(f"成績落後預期 {abs(gap):.3f}（運氣偏差，買點）")

    # Improvement vs their own season baseline — the "something changed" signal.
    if season:
        barrel_delta = _delta(barrel, season.get("barrel_rate"))
        if barrel_delta is not None and barrel_delta >= 5:
            score += 20
            reasons.append(f"barrel% 較整季 +{barrel_delta}")
        xwoba_delta = _delta(xwoba, season.get("xwoba"))
        if xwoba_delta is not None and xwoba_delta >= 0.050:
            score += 15
            reasons.append(f"xwOBA 較整季 +{xwoba_delta:.3f}")

    return score, reasons


def _score_pitcher(recent: dict, season: dict | None) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    whiff = recent.get("whiff_rate")
    csw = recent.get("csw_rate")
    xwoba_allowed = recent.get("xwoba")
    velo = recent.get("avg_fastball_velo")

    # CSW% is the steadier read on stuff (denominator is every pitch), so it
    # leads; whiff% only speaks up when CSW is unavailable.
    if csw is not None and csw >= 33:
        score += 25
        reasons.append(f"近期 CSW% {csw}（頂級）")
    elif csw is not None and csw >= 30:
        score += 15
        reasons.append(f"近期 CSW% {csw}（優異）")
    elif whiff is not None and whiff >= 32:
        score += 25
        reasons.append(f"近期 whiff% {whiff}（優異）")
    elif whiff is not None and whiff >= 27:
        score += 12
        reasons.append(f"近期 whiff% {whiff}")

    if xwoba_allowed is not None and xwoba_allowed <= 0.280:
        score += 25
        reasons.append(f"被打 xwOBA {xwoba_allowed:.3f}（壓制）")
    elif xwoba_allowed is not None and xwoba_allowed <= 0.310:
        score += 12
        reasons.append(f"被打 xwOBA {xwoba_allowed:.3f}")

    if season:
        velo_delta = _delta(velo, season.get("avg_fastball_velo"))
        if velo_delta is not None and velo_delta >= 1.0:
            score += 20
            reasons.append(f"速球均速 較整季 +{velo_delta} mph（狀態/角色改變）")
        elif velo_delta is not None and velo_delta <= -1.5:
            # Surfaced as a warning, not a buy signal.
            reasons.append(f"⚠ 速球均速 較整季 {velo_delta} mph（傷兵風險）")

        whiff_delta = _delta(whiff, season.get("whiff_rate"))
        if whiff_delta is not None and whiff_delta >= 5:
            score += 15
            reasons.append(f"whiff% 較整季 +{whiff_delta}")

        csw_delta = _delta(csw, season.get("csw_rate"))
        if csw_delta is not None and csw_delta >= 3:
            score += 15
            reasons.append(f"CSW% 較整季 +{csw_delta}")

    # ERA well above FIP means the damage was luck/defence, not the pitcher —
    # exactly the profile the market under-rates.
    fip = recent.get("fip")
    era_gap = recent.get("era_minus_fip")
    if fip is not None and era_gap is not None and era_gap >= 1.0:
        score += 20
        reasons.append(f"ERA 比 FIP 高 {era_gap}（運氣/守備拖累，買點）")

    return score, reasons


def build_radar(
    year: int,
    as_of: date,
    role: str = "batter",
    window_days: int = RECENT_WINDOW_DAYS,
    limit: int = 25,
    include_owned: bool = False,
) -> dict:
    """Rank unowned players by recent underlying performance.

    Returns {"window": ..., "players": [...], "coverage": ...}. An empty player
    list with a populated `notes` field means "no data", never "nobody qualifies".
    """
    from api.database import get_statcast_coverage, get_statcast_window
    from src.notification.scheduler import (
        _build_current_owner_lookup,
        _normalize_player_name,
    )

    notes: list[str] = []
    recent_start = as_of - timedelta(days=window_days - 1)
    season_start = date(year, 3, 1)

    coverage = get_statcast_coverage()
    if not coverage.get("days"):
        return {
            "window": {"start": recent_start.isoformat(), "end": as_of.isoformat()},
            "players": [],
            "coverage": coverage,
            "notes": ["尚未匯入 Statcast 資料，請先執行同步。"],
        }

    min_pa = MIN_RECENT_PA_BATTER if role == "batter" else 0
    recent_rows = get_statcast_window(recent_start, as_of, role, min_pa=min_pa)
    season_rows = get_statcast_window(season_start, as_of, role)
    season_by_id = {r["player_id"]: summarize(r) for r in season_rows}

    # FIP needs innings pitched, which Statcast does not carry — merge it from
    # the official MLB lines, keyed by MLB player id (both sources use it).
    fip_recent: dict[int, dict] = {}
    fip_season: dict[int, dict] = {}
    if role == "pitcher":
        try:
            from api.database import get_mlb_pitching_window
            from src.analytics.mlb_pitching import (
                league_fip_constant,
                summarize_pitching,
            )

            def _fip_index(rows):
                constant = league_fip_constant(rows)
                return {
                    r["player_id"]: summarize_pitching(r, constant) for r in rows
                }

            fip_recent = _fip_index(get_mlb_pitching_window(recent_start, as_of))
            fip_season = _fip_index(get_mlb_pitching_window(season_start, as_of))
            if not fip_recent:
                notes.append("官方投球數據暫缺，FIP 未納入評分。")
        except Exception as e:
            print(f"[Radar] FIP merge skipped: {e}", flush=True)
            notes.append("官方投球數據載入失敗，FIP 未納入評分。")

    owner_by_name, owner_debug = _build_current_owner_lookup(year)
    if not owner_by_name:
        notes.append("持有名單暫缺，結果未排除已被選走的球員。")

    scorer = _score_batter if role == "batter" else _score_pitcher
    results: list[dict] = []

    for row in recent_rows:
        recent = summarize(row)
        if role == "pitcher" and recent["pitches"] < MIN_RECENT_PITCHES_PITCHER:
            continue

        name = recent.get("player_name") or ""
        if not name:
            continue

        owner = owner_by_name.get(_normalize_player_name(name))
        is_owned = bool(owner)
        if is_owned and not include_owned:
            continue

        season = season_by_id.get(recent["player_id"])

        if role == "pitcher":
            for profile, source in ((recent, fip_recent), (season, fip_season)):
                extra = source.get(recent["player_id"])
                if profile is not None and extra:
                    profile["fip"] = extra["fip"]
                    profile["ip"] = extra["ip"]
                    profile["era"] = extra["era"]
                    profile["era_minus_fip"] = extra["era_minus_fip"]

        score, reasons = scorer(recent, season)
        if score <= 0:
            continue

        results.append({
            "player_id": recent["player_id"],
            "name": name,
            "score": round(score, 1),
            "reasons": reasons,
            "recent": recent,
            "season": season,
            "owned": is_owned,
            "owner_team": (owner or {}).get("owner_team_name", ""),
            "owner_manager": (owner or {}).get("owner_manager", ""),
        })

    results.sort(key=lambda r: -r["score"])

    return {
        "window": {
            "start": recent_start.isoformat(),
            "end": as_of.isoformat(),
            "days": window_days,
        },
        "role": role,
        "players": results[:limit],
        "total_candidates": len(results),
        "coverage": coverage,
        "ownership": {
            "sources": owner_debug.get("source", []),
            "players": len(owner_by_name),
        },
        "notes": notes,
    }
