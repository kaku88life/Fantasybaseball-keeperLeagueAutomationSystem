"""
Fantasy Baseball Keeper League - Analytics Routes (auth required)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_current_user

router = APIRouter()


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
