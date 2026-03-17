"""
Fantasy Baseball Keeper League - Draft/FAAB Analytics Routes (public)
"""
from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/draft-stats")
async def get_draft_stats(
    years: str = Query(default="", description="Comma-separated years, empty = all"),
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
):
    """Get per-team trade activity statistics."""
    from src.analytics.draft_stats import compute_trade_stats

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]

    return compute_trade_stats(year_list or None)
