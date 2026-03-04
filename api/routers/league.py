"""
Fantasy Baseball Keeper League - League Data Routes (read-only)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.database import get_snapshot, get_snapshot_years
from api.schemas import LeagueSettingsSchema, LeagueSnapshotSchema
from api.serializers import dict_to_league_state, serialize_league_state, serialize_team

router = APIRouter()


@router.get("/settings", response_model=LeagueSettingsSchema)
async def get_league_settings():
    """Return league rule settings."""
    from config.settings import (
        CONTRACT_TYPES,
        EXTENSION_COST_PER_YEAR,
        FAAB_BASE,
        HITTING_CATS,
        KEEPER_ACTIVE_MAX,
        KEEPER_ACTIVE_MIN,
        KEEPER_BENCH_MAX,
        LEAGUE_NAME,
        MIN_BID,
        PITCHING_CATS,
        RANKING_BONUS,
        ROSTER_POSITIONS,
        SALARY_BASE,
        SALARY_INCREMENT,
        SCORING_FORMAT,
        TOTAL_TEAMS,
    )
    return LeagueSettingsSchema(
        league_name=LEAGUE_NAME,
        total_teams=TOTAL_TEAMS,
        scoring_format=SCORING_FORMAT,
        hitting_cats=HITTING_CATS,
        pitching_cats=PITCHING_CATS,
        salary_base=SALARY_BASE,
        salary_increment=SALARY_INCREMENT,
        faab_base=FAAB_BASE,
        min_bid=MIN_BID,
        keeper_active_min=KEEPER_ACTIVE_MIN,
        keeper_active_max=KEEPER_ACTIVE_MAX,
        keeper_bench_max=KEEPER_BENCH_MAX,
        extension_cost_per_year=EXTENSION_COST_PER_YEAR,
        contract_types=CONTRACT_TYPES,
        ranking_bonus=RANKING_BONUS,
        roster_positions=ROSTER_POSITIONS,
    )


@router.get("/years")
async def list_years() -> list[int]:
    """Return all available snapshot years."""
    return get_snapshot_years()


@router.get("/{year}", response_model=LeagueSnapshotSchema)
async def get_league_year(year: int):
    """Return league snapshot for a specific year."""
    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    return serialize_league_state(ls)


@router.get("/{year}/summary")
async def get_league_summary(year: int):
    """Return a summary of all teams for a year."""
    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    summary = []
    for t in ls.teams:
        summary.append({
            "manager_name": t.manager_name,
            "team_name": t.team_name,
            "active_keepers": len(t.active_keepers),
            "bench_keepers": len(t.bench_keepers),
            "total_keeper_cost": t.total_keeper_cost,
            "total_buyout_cost": t.total_buyout_cost,
            "available_salary": t.available_salary,
            "available_faab": t.available_faab,
            "salary_cap": t.salary_cap,
            "ranking_bonus": t.ranking_bonus,
        })
    return {
        "year": year,
        "salary_cap": ls.salary_cap,
        "teams": summary,
    }
