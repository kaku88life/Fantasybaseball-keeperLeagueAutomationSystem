"""
Fantasy Baseball Keeper League - Analytics Routes (auth required)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.dependencies import get_current_user

router = APIRouter()


class StatcastLookupPlayer(BaseModel):
    name: str
    is_pitcher: bool = False


class StatcastLookupRequest(BaseModel):
    """Batch lookup so a 50-row table costs one request, not 50."""
    players: list[StatcastLookupPlayer] = Field(default_factory=list, max_length=200)
    window_days: int = Field(default=15, ge=3, le=60)
    year: int = 0


@router.post("/statcast-lookup")
async def statcast_lookup(
    payload: StatcastLookupRequest,
    _user: dict = Depends(get_current_user),
):
    """Resolve many players' Statcast profiles by name in one call.

    Name normalisation happens here only. The response is keyed by the exact
    name the caller sent, so the frontend never has to reimplement the matching
    rules (and cannot drift from them).
    """
    from datetime import date as _date, timedelta as _timedelta

    from api.database import get_statcast_window
    from src.analytics.statcast import summarize
    from src.notification.scheduler import _normalize_player_name

    today = _date.today()
    season = payload.year or today.year
    recent_start = today - _timedelta(days=payload.window_days - 1)
    season_start = _date(season, 3, 1)

    if not payload.players:
        return {"results": {}, "window": {"start": recent_start.isoformat(),
                                          "end": today.isoformat()}}

    def index(rows):
        out = {}
        for row in rows:
            profile = summarize(row)
            key = _normalize_player_name(profile.get("player_name", ""))
            if key:
                out[key] = profile
        return out

    indexed = {
        role: {
            "recent": index(get_statcast_window(recent_start, today, role)),
            "season": index(get_statcast_window(season_start, today, role)),
        }
        for role in ("batter", "pitcher")
    }

    # Official pitching lines carry innings pitched, which Statcast lacks, so
    # FIP is merged in from there rather than inferred.
    from api.database import get_mlb_pitching_window
    from src.analytics.mlb_pitching import league_fip_constant, summarize_pitching

    def index_pitching(rows):
        constant = league_fip_constant(rows)
        out = {}
        for row in rows:
            summary = summarize_pitching(row, constant)
            key = _normalize_player_name(summary.get("player_name", ""))
            if key:
                out[key] = summary
        return out

    try:
        official = {
            "recent": index_pitching(get_mlb_pitching_window(recent_start, today)),
            "season": index_pitching(get_mlb_pitching_window(season_start, today)),
        }
    except Exception as e:
        print(f"[StatcastLookup] official pitching merge skipped: {e}")
        official = {"recent": {}, "season": {}}

    results: dict[str, dict] = {}
    for player in payload.players:
        key = _normalize_player_name(player.name)
        if not key:
            continue
        role = "pitcher" if player.is_pitcher else "batter"
        recent = indexed[role]["recent"].get(key)
        season_profile = indexed[role]["season"].get(key)
        if player.is_pitcher:
            for window_name, profile in (("recent", recent), ("season", season_profile)):
                extra = official[window_name].get(key)
                if profile is not None and extra:
                    profile["fip"] = extra["fip"]
                    profile["ip"] = extra["ip"]
                    profile["era"] = extra["era"]
                    profile["era_minus_fip"] = extra["era_minus_fip"]
        if recent or season_profile:
            results[player.name] = {"recent": recent, "season": season_profile}

    # Actual ingested coverage — the "season" aggregate is only as complete as
    # what has been imported, so the UI must be able to say so.
    from api.database import get_statcast_coverage

    try:
        coverage = get_statcast_coverage() or {}
        coverage_first = coverage.get("first_date")
    except Exception:
        coverage_first = None

    return {
        "results": results,
        "window": {"start": recent_start.isoformat(), "end": today.isoformat(),
                   "days": payload.window_days},
        "season_window": {
            "start": season_start.isoformat(),
            "end": today.isoformat(),
            "coverage_start": coverage_first.isoformat() if coverage_first else None,
        },
        "matched": len(results),
        "requested": len(payload.players),
    }


@router.get("/fa-radar")
async def get_fa_radar(
    year: int = Query(default=0, description="Season, 0 = current year"),
    role: str = Query(default="batter", pattern="^(batter|pitcher)$"),
    window_days: int = Query(default=15, ge=3, le=60),
    limit: int = Query(default=25, ge=1, le=100),
    include_owned: bool = Query(default=False, description="Include rostered players"),
    _user: dict = Depends(get_current_user),
):
    """Unowned players whose recent Statcast profile is trending up."""
    from datetime import date as _date

    from src.analytics.fa_radar import build_radar

    today = _date.today()
    return build_radar(
        year=year or today.year,
        as_of=today,
        role=role,
        window_days=window_days,
        limit=limit,
        include_owned=include_owned,
    )


@router.get("/statcast-coverage")
async def get_statcast_coverage_endpoint(_user: dict = Depends(get_current_user)):
    """How much Statcast history is ingested — drives the UI's freshness note."""
    from api.database import get_statcast_coverage

    coverage = get_statcast_coverage()
    return {
        "first_date": (
            coverage["first_date"].isoformat() if coverage.get("first_date") else None
        ),
        "last_date": (
            coverage["last_date"].isoformat() if coverage.get("last_date") else None
        ),
        "days": coverage.get("days", 0),
    }


@router.get("/player-statcast/{player_id}")
async def get_player_statcast(
    player_id: int,
    year: int = Query(default=0),
    window_days: int = Query(default=15, ge=3, le=60),
    role: str = Query(default="batter", pattern="^(batter|pitcher)$"),
    _user: dict = Depends(get_current_user),
):
    """Recent vs season Statcast profile for one player."""
    from datetime import date as _date, timedelta as _timedelta

    from api.database import get_statcast_window
    from src.analytics.statcast import summarize

    today = _date.today()
    season = year or today.year
    recent_start = today - _timedelta(days=window_days - 1)

    def _find(rows):
        for row in rows:
            if row["player_id"] == player_id:
                return summarize(row)
        return None

    return {
        "player_id": player_id,
        "role": role,
        "recent": _find(get_statcast_window(recent_start, today, role)),
        "season": _find(get_statcast_window(_date(season, 3, 1), today, role)),
        "window": {"start": recent_start.isoformat(), "end": today.isoformat()},
    }


@router.get("/draft-stats")
async def get_draft_stats(
    years: str = Query(default="", description="Comma-separated years, empty = all"),
    _user: dict = Depends(get_current_user),
):
    """Get per-team draft spending statistics."""
    from src.analytics.draft_stats import compute_draft_stats

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]

    return compute_draft_stats(year_list or None)


@router.get("/faab-stats")
async def get_faab_stats(
    years: str = Query(default="", description="Comma-separated years, empty = all"),
    _user: dict = Depends(get_current_user),
):
    """Get per-team FAAB spending statistics."""
    from src.analytics.draft_stats import compute_faab_stats

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]

    return compute_faab_stats(year_list or None)


@router.get("/position-preference")
async def get_position_preference(
    years: str = Query(default="", description="Comma-separated years, empty = all"),
    min_cost: int = Query(default=20, description="Minimum draft cost to include"),
    _user: dict = Depends(get_current_user),
):
    """Get draft position preference analysis ($20+ picks)."""
    from src.analytics.draft_stats import compute_position_preference

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]

    return compute_position_preference(year_list or None, min_cost=min_cost)


@router.get("/trade-stats")
async def get_trade_stats(
    years: str = Query(default="", description="Comma-separated years, empty = all"),
    _user: dict = Depends(get_current_user),
):
    """Get per-team trade activity statistics."""
    from src.analytics.draft_stats import compute_trade_stats

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]

    return compute_trade_stats(year_list or None)


@router.get("/salary-rankings")
async def get_salary_rankings(
    years: str = Query(default="", description="Comma-separated years, empty = all"),
    _user: dict = Depends(get_current_user),
):
    """Get per-year Top 20 salary rankings (keepers + draft)."""
    from src.analytics.draft_stats import compute_salary_rankings

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]

    return compute_salary_rankings(year_list or None)


@router.get("/contract-values")
async def get_contract_values(_user: dict = Depends(get_current_user)):
    """Get all-time N-contract total value rankings."""
    from src.analytics.draft_stats import compute_contract_values

    return compute_contract_values()


@router.get("/league-summary")
async def get_league_summary(_user: dict = Depends(get_current_user)):
    """Get league-wide summary/overview stats."""
    from src.analytics.draft_stats import compute_league_summary

    return compute_league_summary()
