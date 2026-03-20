"""
Fantasy Baseball Keeper League - Public API (no auth required)

Designed for AI tools (Claude, Gemini, ChatGPT) to read league context.
Endpoints return plain-text or JSON with complete league rules and team data.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from api.database import get_all_teams, get_snapshot
from api.serializers import dict_to_league_state, serialize_player

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_settings_text() -> str:
    """Build a human-readable league rules summary."""
    from config.settings import (
        LEAGUE_NAME, TOTAL_TEAMS, SCORING_FORMAT,
        HITTING_CATS, PITCHING_CATS, MIN_IP,
        SALARY_BASE, SALARY_INCREMENT, SALARY_START_YEAR,
        FAAB_BASE, MIN_BID, SHUTOUT_FAAB_BONUS,
        KEEPER_ACTIVE_MIN, KEEPER_ACTIVE_MAX, KEEPER_BENCH_MAX,
        EXTENSION_COST_PER_YEAR, FAAB_KEEPER_THRESHOLD,
        RANKING_BONUS, ROOKIE_IP_THRESHOLD, ROOKIE_PA_THRESHOLD,
        get_salary_cap,
    )
    current_year = datetime.now().year
    cap = get_salary_cap(current_year)

    lines = [
        f"# {LEAGUE_NAME} - League Rules",
        f"",
        f"## Basic Info",
        f"- Teams: {TOTAL_TEAMS}",
        f"- Format: {SCORING_FORMAT}",
        f"- Hitting: {', '.join(HITTING_CATS)}",
        f"- Pitching: {', '.join(PITCHING_CATS)}",
        f"- Min IP per matchup: {MIN_IP}",
        f"",
        f"## Salary Cap ({current_year})",
        f"- Base: ${SALARY_BASE} (2023)",
        f"- Increment: +${SALARY_INCREMENT}/year from {SALARY_START_YEAR}",
        f"- Current ({current_year}): ${cap}",
        f"- Formula: ${SALARY_BASE} + (year - {SALARY_START_YEAR} + 1) x ${SALARY_INCREMENT}",
        f"",
        f"## FAAB",
        f"- Annual budget: ${FAAB_BASE}",
        f"- Min bid: ${MIN_BID} ($0 bids invalid)",
        f"- Shutout bonus: +${SHUTOUT_FAAB_BONUS}",
        f"- FAAB >= ${FAAB_KEEPER_THRESHOLD} -> mandatory keeper",
        f"",
        f"## Keeper Rules",
        f"- Active keepers: {KEEPER_ACTIVE_MIN}-{KEEPER_ACTIVE_MAX}",
        f"- Farm rookies (R contract): max {KEEPER_BENCH_MAX}",
        f"",
        f"## Contract System",
        f"- A (year 1) -> B (year 2) -> O (option/final) -> FA",
        f"- B can extend N years: salary + N x ${EXTENSION_COST_PER_YEAR}",
        f"- N contracts auto-continue (mandatory keeper)",
        f"- R (rookie): does NOT count toward {KEEPER_ACTIVE_MAX}-man limit",
        f"- Rookie eligibility: IP <= {ROOKIE_IP_THRESHOLD}, PA <= {ROOKIE_PA_THRESHOLD}",
        f"",
        f"## Ranking Bonus (from previous year playoffs)",
    ]
    for place, bonus in sorted(RANKING_BONUS.items()):
        lines.append(f"- {place}st/nd/rd/th: +${bonus}")

    lines.extend([
        f"",
        f"## Buyout Rules",
        f"- Normal: full salary x remaining years from salary cap",
        f"- FAAB buyout: ceil(salary/2) from FAAB + floor(salary/2) from cap",
        f"",
        f"## Trade Rules",
        f"- Salary: use higher of original vs trade price",
        f"- Contract: use longer remaining contract",
    ])

    return "\n".join(lines)


def _build_team_text(team, db_team: dict) -> str:
    """Build text representation of a team's roster and financials."""
    lines = [
        f"## {team.manager_name} ({team.team_name})",
        f"",
        f"### Financials",
        f"- Salary cap: ${team.salary_cap}",
        f"- Ranking bonus: +${team.ranking_bonus}",
        f"- Trade compensation: ${team.trade_compensation}",
        f"- Keeper cost: ${team.total_keeper_cost}",
        f"- Buyout cost (salary): ${team.total_buyout_cost}",
        f"- Buyout cost (FAAB): ${team.total_buyout_faab_cost}",
        f"- Available salary: ${team.available_salary}",
        f"- Available FAAB: ${team.available_faab}",
        f"- Active keepers: {len(team.active_keepers)}/{15}",
        f"- Farm rookies: {len(team.farm_rookies)}/2",
        f"",
        f"### Roster",
    ]

    # Group by contract type
    players_by_type: dict[str, list] = {}
    for p in team.players:
        ct = p.contract.contract_type
        if ct not in players_by_type:
            players_by_type[ct] = []
        players_by_type[ct].append(p)

    for ct in ["A", "B", "N", "O", "R"]:
        group = players_by_type.get(ct, [])
        if not group:
            # Check N1, N2, N3, etc.
            n_players = [
                p for key, plist in players_by_type.items()
                if key.startswith("N") for p in plist
            ] if ct == "N" else []
            if ct == "N" and n_players:
                group = n_players
            else:
                continue

        lines.append(f"")
        lines.append(f"#### {ct} Contract")
        lines.append(f"| Player | Position | Salary | Contract | MLB Team |")
        lines.append(f"|--------|----------|--------|----------|----------|")
        for p in sorted(group, key=lambda x: -x.contract.salary):
            ct_display = p.contract.contract_type
            if ct_display.startswith("N"):
                ct_display = f"N{p.contract.extension_years}"
            lines.append(
                f"| {p.name} | {p.position} | ${p.contract.salary} | {ct_display} | {p.mlb_team or '?'} |"
            )

    # Buyout records
    if team.buyout_records:
        lines.append(f"")
        lines.append(f"### Buyout Records")
        lines.append(f"| Player | Original Contract | Salary Cost | FAAB Cost | Years |")
        lines.append(f"|--------|-------------------|-------------|-----------|-------|")
        for bo in team.buyout_records:
            lines.append(
                f"| {bo.player_name} | {bo.original_contract} | ${bo.buyout_salary_cost} | ${bo.buyout_faab_cost} | {bo.remaining_years} |"
            )

    return "\n".join(lines)


@router.get("/context/{year}", response_class=PlainTextResponse)
async def get_league_context(year: int):
    """Get complete league context for AI analysis.

    Returns a plain-text document with league rules + all 16 teams' rosters,
    contracts, and financials. Designed to be pasted into AI tools.

    No authentication required.
    """
    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    db_teams = get_all_teams()
    db_team_map = {t["manager_name"]: t for t in db_teams}

    # Build complete context
    sections = []

    # Header
    sections.append(f"# Fantasy Baseball Keeper League - {year} Season Context")
    sections.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    sections.append(f"# URL: https://5man-keeperleague.zeabur.app")
    sections.append(f"# API: https://fantasybaseball-keeperleague.zeabur.app")
    sections.append(f"")

    # Rules
    sections.append(_load_settings_text())
    sections.append(f"")

    # All teams
    sections.append(f"---")
    sections.append(f"# {year} Season - All Teams")
    sections.append(f"")

    for t in sorted(ls.teams, key=lambda x: x.manager_name):
        db_team = db_team_map.get(t.manager_name, {})

        # Apply DB adjustments
        db_trade_comp = db_team.get("trade_compensation", 0) or 0
        db_faab_adj = db_team.get("faab_adjustment", 0) or 0
        if db_trade_comp != 0:
            t.trade_compensation = db_trade_comp
        if db_faab_adj != 0:
            t.faab_budget = t.faab_budget + db_faab_adj

        # Load buyouts
        from api.database import get_team_buyouts
        team_id = db_team.get("id")
        if team_id:
            from src.contract.models import BuyoutRecord
            db_buyouts = get_team_buyouts(team_id, year)
            for bo in db_buyouts:
                t.buyout_records.append(BuyoutRecord(
                    player_name=bo["player_name"],
                    original_contract=bo["original_contract"],
                    buyout_salary_cost=bo["buyout_salary"],
                    buyout_faab_cost=bo["buyout_faab"],
                    remaining_years=bo["remaining_years"],
                    use_faab=bo["use_faab"],
                    note=bo.get("notes", ""),
                ))

        sections.append(_build_team_text(t, db_team))
        sections.append(f"")
        sections.append(f"---")
        sections.append(f"")

    return "\n".join(sections)


@router.get("/team/{year}/{team_id}", response_class=PlainTextResponse)
async def get_team_context(year: int, team_id: int):
    """Get single team context for AI analysis.

    Returns a plain-text document with league rules + one team's
    complete roster, contracts, and financials.
    """
    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    db_teams = get_all_teams()

    # Find team by DB id
    db_team = None
    for t in db_teams:
        if t["id"] == team_id:
            db_team = t
            break
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Find in snapshot
    target_team = None
    for t in ls.teams:
        if t.manager_name == db_team["manager_name"]:
            target_team = t
            break
    if not target_team:
        raise HTTPException(status_code=404, detail="Team not in snapshot")

    # Apply adjustments
    db_trade_comp = db_team.get("trade_compensation", 0) or 0
    db_faab_adj = db_team.get("faab_adjustment", 0) or 0
    if db_trade_comp != 0:
        target_team.trade_compensation = db_trade_comp
    if db_faab_adj != 0:
        target_team.faab_budget = target_team.faab_budget + db_faab_adj

    from api.database import get_team_buyouts
    from src.contract.models import BuyoutRecord
    db_buyouts = get_team_buyouts(team_id, year)
    for bo in db_buyouts:
        target_team.buyout_records.append(BuyoutRecord(
            player_name=bo["player_name"],
            original_contract=bo["original_contract"],
            buyout_salary_cost=bo["buyout_salary"],
            buyout_faab_cost=bo["buyout_faab"],
            remaining_years=bo["remaining_years"],
            use_faab=bo["use_faab"],
            note=bo.get("notes", ""),
        ))

    sections = [
        f"# Fantasy Baseball Keeper League - {year} Season",
        f"# Team: {target_team.manager_name} ({target_team.team_name})",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        _load_settings_text(),
        f"",
        f"---",
        f"",
        _build_team_text(target_team, db_team),
    ]

    return "\n".join(sections)


@router.get("/teams/{year}")
async def list_teams_public(year: int):
    """List all teams with basic info (for AI to pick team_id)."""
    db_teams = get_all_teams()
    return [
        {
            "id": t["id"],
            "manager_name": t["manager_name"],
            "team_name": t.get("team_name", ""),
        }
        for t in db_teams
    ]
