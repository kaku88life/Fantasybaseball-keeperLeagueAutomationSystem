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

from api.database import get_all_teams, get_keeper_selections, get_player_rankings, get_snapshot
from api.helpers import apply_db_adjustments
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

    # Group by contract type (convert enum to string)
    players_by_type: dict[str, list] = {}
    for p in team.players:
        ct = str(p.contract.contract_type.value) if hasattr(p.contract.contract_type, 'value') else str(p.contract.contract_type)
        if ct not in players_by_type:
            players_by_type[ct] = []
        players_by_type[ct].append(p)

    for ct in ["A", "B", "N", "O", "R"]:
        group = players_by_type.get(ct, [])
        if not group:
            # Check N1, N2, N3, etc.
            n_players = [
                p for key, plist in players_by_type.items()
                if str(key).startswith("N") for p in plist
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
            ct_raw = str(p.contract.contract_type.value) if hasattr(p.contract.contract_type, 'value') else str(p.contract.contract_type)
            ct_display = ct_raw
            if str(ct_display).startswith("N"):
                ext = getattr(p.contract, 'extension_years', 0) or 0
                ct_display = f"N{ext}" if ext else ct_display
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
        apply_db_adjustments(t, db_team, year)

        sections.append(_build_team_text(t, db_team))

        # Keeper selections for this team
        team_id = db_team.get("id")
        if team_id:
            selections = get_keeper_selections(year, team_id)
            if selections:
                sections.append(f"")
                sections.append(f"### Keeper Decisions")
                sections.append(f"| Player | Current Contract | Action | Extension | Next Contract |")
                sections.append(f"|--------|-----------------|--------|-----------|---------------|")
                for sel in selections:
                    ext = f"{sel['extension_years']}yr" if sel.get('extension_years') else "-"
                    sections.append(
                        f"| {sel['player_name']} | {sel['current_contract']} | {sel['action']} | {ext} | {sel.get('next_contract', '-')} |"
                    )

        sections.append(f"")
        sections.append(f"---")
        sections.append(f"")

    # Collect all rostered player names for FA detection
    all_rostered: set[str] = set()
    for t in ls.teams:
        for p in t.players:
            all_rostered.add(p.name)

    # Player rankings / projections
    try:
        rankings = get_player_rankings(year)
    except Exception:
        rankings = []

    if rankings:
        # Top ranked players
        top_players = [r for r in rankings if r.get("o_rank") and r["o_rank"] <= 100]
        if top_players:
            sections.append(f"# {year} Player Rankings (Top 100)")
            sections.append(f"")
            sections.append(f"| Rank | Player | Position | Team | Status | Proj HR | Proj RBI | Proj SB | Proj AVG | Proj W | Proj K | Proj ERA |")
            sections.append(f"|------|--------|----------|------|--------|---------|----------|---------|----------|--------|--------|----------|")
            for r in sorted(top_players, key=lambda x: x["o_rank"]):
                status = "Rostered" if r["player_name"] in all_rostered else "FA"
                sections.append(
                    f"| {r['o_rank']} | {r['player_name']} | {r.get('position', '?')} | {r.get('mlb_team', '?')} | {status} "
                    f"| {r.get('proj_hr') or '-'} | {r.get('proj_rbi') or '-'} | {r.get('proj_sb') or '-'} "
                    f"| {r.get('proj_avg') or '-'} | {r.get('proj_w') or '-'} | {r.get('proj_k') or '-'} "
                    f"| {r.get('proj_era') or '-'} |"
                )
            sections.append(f"")

        # Free agents: ranked players not on any roster
        fa_players = [r for r in rankings if r["player_name"] not in all_rostered and r.get("o_rank")]
        fa_players.sort(key=lambda x: x["o_rank"])
        if fa_players:
            sections.append(f"---")
            sections.append(f"# {year} Free Agents (Not on any team, by ranking)")
            sections.append(f"")
            sections.append(f"| Rank | Player | Position | MLB Team |")
            sections.append(f"|------|--------|----------|----------|")
            for r in fa_players[:50]:
                sections.append(
                    f"| {r['o_rank']} | {r['player_name']} | {r.get('position', '?')} | {r.get('mlb_team', '?')} |"
                )
            if len(fa_players) > 50:
                sections.append(f"")
                sections.append(f"... and {len(fa_players) - 50} more free agents")
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
    apply_db_adjustments(target_team, db_team, year)

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


def _get_all_rostered_names(year: int) -> set[str]:
    """Get set of all rostered player names across all teams."""
    snap = get_snapshot(year)
    if not snap:
        return set()
    ls = dict_to_league_state(snap["data"])
    names: set[str] = set()
    for t in ls.teams:
        for p in t.players:
            names.add(p.name)
    return names


_HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH", "Util"}
_PITCHER_POSITIONS = {"SP", "RP", "P"}


def _is_hitter(position: str) -> bool:
    if not position:
        return False
    primary = position.split(",")[0].strip()
    return primary in _HITTER_POSITIONS


def _is_pitcher(position: str) -> bool:
    if not position:
        return False
    primary = position.split(",")[0].strip()
    return primary in _PITCHER_POSITIONS


@router.get("/fa/hitters/{year}", response_class=PlainTextResponse)
async def get_fa_hitters(year: int):
    """Free agent hitters ranked by overall rank.

    Returns plain-text table of hitters not on any team's roster,
    with previous season stats and current season projections.
    """
    rostered = _get_all_rostered_names(year)
    try:
        rankings = get_player_rankings(year)
    except Exception:
        rankings = []

    fa_hitters = [
        r for r in rankings
        if r["player_name"] not in rostered
        and r.get("o_rank")
        and _is_hitter(r.get("position", ""))
    ]
    fa_hitters.sort(key=lambda x: x["o_rank"])

    lines = [
        f"# {year} Free Agent Hitters",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Total: {len(fa_hitters)} hitters available",
        f"",
        f"| Rank | Player | Pos | MLB Team | Prev R | Prev H | Prev HR | Prev RBI | Prev SB | Prev AVG | Prev OPS | Proj R | Proj H | Proj HR | Proj RBI | Proj SB | Proj AVG | Proj OPS |",
        f"|------|--------|-----|----------|--------|--------|---------|----------|---------|----------|----------|--------|--------|---------|----------|---------|----------|----------|",
    ]

    for r in fa_hitters:
        lines.append(
            f"| {r['o_rank']} | {r['player_name']} | {r.get('position', '?')} | {r.get('mlb_team', '?')} "
            f"| {r.get('stat_r') or '-'} | {r.get('stat_h') or '-'} | {r.get('stat_hr') or '-'} "
            f"| {r.get('stat_rbi') or '-'} | {r.get('stat_sb') or '-'} "
            f"| {r.get('stat_avg') or '-'} | {r.get('stat_ops') or '-'} "
            f"| {r.get('proj_r') or '-'} | {r.get('proj_h') or '-'} | {r.get('proj_hr') or '-'} "
            f"| {r.get('proj_rbi') or '-'} | {r.get('proj_sb') or '-'} "
            f"| {r.get('proj_avg') or '-'} | {r.get('proj_ops') or '-'} |"
        )

    return "\n".join(lines)


@router.get("/fa/pitchers/{year}", response_class=PlainTextResponse)
async def get_fa_pitchers(year: int):
    """Free agent pitchers ranked by overall rank.

    Returns plain-text table of pitchers not on any team's roster,
    with previous season stats and current season projections.
    """
    rostered = _get_all_rostered_names(year)
    try:
        rankings = get_player_rankings(year)
    except Exception:
        rankings = []

    fa_pitchers = [
        r for r in rankings
        if r["player_name"] not in rostered
        and r.get("o_rank")
        and _is_pitcher(r.get("position", ""))
    ]
    fa_pitchers.sort(key=lambda x: x["o_rank"])

    lines = [
        f"# {year} Free Agent Pitchers",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Total: {len(fa_pitchers)} pitchers available",
        f"",
        f"| Rank | Player | Pos | MLB Team | Prev W | Prev SV | Prev HLD | Prev K | Prev ERA | Prev WHIP | Prev QS | Proj W | Proj SV | Proj HLD | Proj K | Proj ERA | Proj WHIP | Proj QS |",
        f"|------|--------|-----|----------|--------|---------|----------|--------|----------|-----------|---------|--------|---------|----------|--------|----------|-----------|---------|",
    ]

    for r in fa_pitchers:
        lines.append(
            f"| {r['o_rank']} | {r['player_name']} | {r.get('position', '?')} | {r.get('mlb_team', '?')} "
            f"| {r.get('stat_w') or '-'} | {r.get('stat_sv') or '-'} | {r.get('stat_hld') or '-'} "
            f"| {r.get('stat_k') or '-'} | {r.get('stat_era') or '-'} "
            f"| {r.get('stat_whip') or '-'} | {r.get('stat_qs') or '-'} "
            f"| {r.get('proj_w') or '-'} | {r.get('proj_sv') or '-'} | {r.get('proj_hld') or '-'} "
            f"| {r.get('proj_k') or '-'} | {r.get('proj_era') or '-'} "
            f"| {r.get('proj_whip') or '-'} | {r.get('proj_qs') or '-'} |"
        )

    return "\n".join(lines)
