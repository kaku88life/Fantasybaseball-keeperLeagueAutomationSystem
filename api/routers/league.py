"""
Fantasy Baseball Keeper League - League Data Routes (read-only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user

from api.database import get_all_submissions, get_all_teams, get_player_rankings, get_snapshot, get_snapshot_years, get_team_buyouts
from api.schemas import LeagueSettingsSchema, LeagueSnapshotSchema
from api.serializers import dict_to_league_state, serialize_league_state, serialize_team
from src.contract.engine import calculate_buyout
from src.contract.models import BuyoutRecord, ContractType

router = APIRouter()


def _build_position_lookup(year: int) -> dict[str, dict]:
    """Build a position/mlb_team lookup from player_rankings (2026 Yahoo data)."""
    rankings = get_player_rankings(year)
    lookup: dict[str, dict] = {}
    for r in rankings:
        pk = r.get("player_key", "")
        entry = {"position": r.get("position", ""), "mlb_team": r.get("mlb_team", "")}
        if pk:
            lookup[pk] = entry
            if ".p." in pk:
                pid = pk.split(".p.")[-1]
                lookup[f"pid:{pid}"] = entry
        name = r.get("player_name", "")
        if name:
            lookup[f"name:{name.lower()}"] = entry
    return lookup


def _enrich_league_positions(ls, year: int):
    """Override all player positions in a LeagueState with 2026 Yahoo data."""
    lookup = _build_position_lookup(year)
    for team in ls.teams:
        for p in team.players:
            entry = None
            if p.yahoo_player_id:
                entry = lookup.get(p.yahoo_player_id)
                if not entry and ".p." in p.yahoo_player_id:
                    pid = p.yahoo_player_id.split(".p.")[-1]
                    entry = lookup.get(f"pid:{pid}")
            if not entry:
                entry = lookup.get(f"name:{p.name.lower()}")
            if entry:
                if entry["position"]:
                    p.position = entry["position"]
                if entry["mlb_team"]:
                    p.mlb_team = entry["mlb_team"]


def _enrich_teams_from_db(ls, db_teams: list[dict], year: int):
    """Load DB-stored buyouts, trade_compensation, and faab_adjustment into team models.

    The league snapshot does NOT contain buyout records (they live in the
    ``buyouts`` DB table) or commissioner adjustments (trade_compensation,
    faab_adjustment stored on the ``teams`` table).  This helper mirrors the
    logic in ``teams.py::_get_team_from_snapshot()`` so that league-level
    endpoints also reflect the correct financial numbers.
    """
    # Map manager_name -> db_team row for quick lookup
    db_map: dict[str, dict] = {t["manager_name"]: t for t in db_teams}
    # Map manager_name -> db team_id
    id_map: dict[str, int] = {t["manager_name"]: t["id"] for t in db_teams}

    for t in ls.teams:
        db_team = db_map.get(t.manager_name)
        if not db_team:
            continue

        # Apply commissioner adjustments (same as _get_team_from_snapshot)
        db_trade_comp = db_team.get("trade_compensation", 0) or 0
        db_faab_adj = db_team.get("faab_adjustment", 0) or 0
        if db_trade_comp != 0:
            t.trade_compensation = db_trade_comp
        if db_faab_adj != 0:
            t.faab_budget = t.faab_budget + db_faab_adj

        # Load buyout records from DB
        team_id = id_map[t.manager_name]
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
async def get_league_year(year: int, _user: dict = Depends(get_current_user)):
    """Return league snapshot for a specific year."""
    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    _enrich_league_positions(ls, year)
    return serialize_league_state(ls)


@router.get("/{year}/summary")
async def get_league_summary(year: int, _user: dict = Depends(get_current_user)):
    """Return a summary of all teams for a year."""
    from api.database import get_team_line_names, get_all_teams as _get_all_teams

    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    _enrich_league_positions(ls, year)

    # Get line names and team IDs
    line_names = get_team_line_names()
    db_teams = _get_all_teams()
    manager_to_team_id = {t["manager_name"]: t["id"] for t in db_teams}

    # Load DB-stored buyouts and commissioner adjustments into team models
    _enrich_teams_from_db(ls, db_teams, year)

    summary = []
    for t in ls.teams:
        team_id = manager_to_team_id.get(t.manager_name)
        summary.append({
            "manager_name": t.manager_name,
            "team_name": t.team_name,
            "active_keepers": len(t.active_keepers),
            "farm_rookies": len(t.farm_rookies),
            "total_keeper_cost": t.total_keeper_cost,
            "total_buyout_cost": t.total_buyout_cost,
            "available_salary": t.available_salary,
            "available_faab": t.available_faab,
            "salary_cap": t.salary_cap,
            "ranking_bonus": t.ranking_bonus,
            "line_name": line_names.get(team_id, "") if team_id else "",
        })
    return {
        "year": year,
        "salary_cap": ls.salary_cap,
        "teams": summary,
    }


@router.get("/{year}/keeper-results")
async def get_keeper_results(year: int, _user: dict = Depends(get_current_user)):
    """Return keeper selection results for all submitted teams (public endpoint)."""
    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])
    _enrich_league_positions(ls, year)

    # Get all DB teams for ID mapping
    db_teams = get_all_teams()

    # Load DB-stored buyouts and commissioner adjustments into team models
    _enrich_teams_from_db(ls, db_teams, year)

    # Build a map: manager_name -> team model (AFTER enrichment so buyouts are loaded)
    team_map = {t.manager_name: t for t in ls.teams}

    db_team_map = {t["id"]: t for t in db_teams}

    # Get line names
    from api.database import get_team_line_names
    line_names = get_team_line_names()

    # Get all submissions for this year
    submissions = get_all_submissions(year)
    sub_map = {s["team_id"]: s for s in submissions}

    results = []
    for db_team in db_teams:
        team_id = db_team["id"]
        manager_name = db_team["manager_name"]
        team_model = team_map.get(manager_name)

        sub = sub_map.get(team_id)
        is_submitted = sub is not None

        kept_players = []
        keeper_cost = 0
        new_buyout_salary_cost = 0
        new_buyout_faab_cost = 0

        if sub and sub.get("selections"):
            for sel in sub["selections"]:
                action = sel.get("action", "")
                if action == "fa":
                    continue
                if action in ("release", "release_normal"):
                    # Calculate buyout cost for N-contract players being released.
                    # Only deduct CURRENT YEAR's portion (buyout is paid annually).
                    # Mirrors teams.py _validate_selections() logic.
                    if team_model:
                        for p in team_model.players:
                            if p.name == sel["player_name"]:
                                if p.contract.contract_type == ContractType.N:
                                    use_faab = action == "release"
                                    buyout = calculate_buyout(p, use_faab=use_faab)
                                    # Per-year cost (from yearly_breakdown[0]), not total
                                    if buyout.yearly_breakdown:
                                        year1 = buyout.yearly_breakdown[0]
                                        new_buyout_salary_cost += year1["salary_cap"]
                                        new_buyout_faab_cost += year1.get("faab", 0)
                                break
                    continue
                # This is a kept player
                next_contract = sel.get("next_contract", "")
                # Parse salary from next_contract (format: $X/Type or FA)
                salary = 0
                if next_contract and next_contract != "FA" and "$" in next_contract:
                    try:
                        salary = int(next_contract.split("$")[1].split("/")[0])
                    except (ValueError, IndexError):
                        salary = 0

                # Get position and mlb_team from team model
                position = ""
                mlb_team = ""
                if team_model:
                    for p in team_model.players:
                        if p.name == sel["player_name"]:
                            position = p.position if hasattr(p, "position") else ""
                            mlb_team = p.mlb_team if hasattr(p, "mlb_team") else ""
                            break

                kept_players.append({
                    "player_name": sel["player_name"],
                    "current_contract": sel.get("current_contract", ""),
                    "next_contract": next_contract,
                    "action": action,
                    "salary": salary,
                    "position": position,
                    "mlb_team": mlb_team,
                })
                keeper_cost += salary

        # Get team financial info
        # trade_compensation already applied by _enrich_teams_from_db
        salary_cap = 0
        ranking_bonus = 0
        trade_comp = db_team.get("trade_compensation", 0) or 0
        carryover_buyout_salary = 0
        carryover_buyout_faab = 0

        if team_model:
            salary_cap = team_model.salary_cap
            ranking_bonus = team_model.ranking_bonus
            # Now correctly reflects DB buyout records (loaded by _enrich_teams_from_db)
            carryover_buyout_salary = team_model.total_buyout_cost
            carryover_buyout_faab = team_model.total_buyout_faab_cost

        total_buyout_cost = carryover_buyout_salary + new_buyout_salary_cost
        total_buyout_faab = carryover_buyout_faab + new_buyout_faab_cost
        available_salary = salary_cap + ranking_bonus + trade_comp - keeper_cost - total_buyout_cost

        # FAAB calculation
        faab_budget = 0
        if team_model:
            faab_budget = team_model.faab_budget
        available_faab = faab_budget - total_buyout_faab

        results.append({
            "team_id": team_id,
            "manager_name": manager_name,
            "team_name": db_team.get("team_name", ""),
            "line_name": line_names.get(team_id, ""),
            "is_submitted": is_submitted,
            "kept_players": kept_players,
            "keeper_cost": keeper_cost,
            "buyout_cost": total_buyout_cost,
            "buyout_faab_cost": total_buyout_faab,
            "ranking_bonus": ranking_bonus,
            "trade_compensation": trade_comp,
            "salary_cap": salary_cap,
            "available_salary": available_salary,
            "faab_budget": faab_budget,
            "available_faab": available_faab,
        })

    return {
        "year": year,
        "teams": results,
    }
