"""
Shared helpers used across multiple routers (teams, league, public).

Consolidates duplicated logic for:
- Position lookup from player_rankings
- DB adjustments (trade_compensation, faab, buyouts) applied to team models
- KeeperSelectionResponse list building
- Keeper options building from contract engine
"""
from __future__ import annotations

from api.database import get_player_rankings, get_team_buyouts
from api.schemas import KeeperSelectionResponse
from src.contract.models import BuyoutRecord


# ---------------------------------------------------------------------------
# Position lookup (was duplicated in teams.py & league.py)
# ---------------------------------------------------------------------------

def build_position_lookup(year: int) -> dict[str, dict]:
    """Build a position/mlb_team lookup from player_rankings (Yahoo data)."""
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


def enrich_player_position(player, lookup: dict[str, dict]):
    """Override a single player's position/mlb_team using lookup."""
    entry = None
    if player.yahoo_player_id:
        entry = lookup.get(player.yahoo_player_id)
        if not entry and ".p." in player.yahoo_player_id:
            pid = player.yahoo_player_id.split(".p.")[-1]
            entry = lookup.get(f"pid:{pid}")
    if not entry:
        entry = lookup.get(f"name:{player.name.lower()}")
    if entry:
        if entry["position"]:
            player.position = entry["position"]
        if entry["mlb_team"]:
            player.mlb_team = entry["mlb_team"]


def enrich_team_positions(team, year: int):
    """Override all player positions in a single team with Yahoo data."""
    lookup = build_position_lookup(year)
    for p in team.players:
        enrich_player_position(p, lookup)


def enrich_league_positions(ls, year: int):
    """Override all player positions across all teams in a LeagueState."""
    lookup = build_position_lookup(year)
    for team in ls.teams:
        for p in team.players:
            enrich_player_position(p, lookup)


# ---------------------------------------------------------------------------
# DB adjustments + buyout loading (was duplicated 4 times)
# ---------------------------------------------------------------------------

def _build_buyout_record(bo: dict) -> BuyoutRecord:
    """Convert a DB buyout row to a BuyoutRecord model."""
    return BuyoutRecord(
        player_name=bo["player_name"],
        original_contract=bo["original_contract"],
        buyout_salary_cost=bo["buyout_salary"],
        buyout_faab_cost=bo["buyout_faab"],
        remaining_years=bo["remaining_years"],
        use_faab=bo["use_faab"],
        note=bo.get("notes", ""),
    )


def apply_db_adjustments(team, db_team: dict, year: int):
    """Apply DB-stored trade_compensation, faab_adjustment, and buyouts to a team model.

    This was previously duplicated in:
    - teams.py::_get_team_from_snapshot
    - league.py::_enrich_teams_from_db
    - public.py::get_league_context
    - public.py::get_team_context
    """
    db_trade_comp = db_team.get("trade_compensation", 0) or 0
    db_faab_adj = db_team.get("faab_adjustment", 0) or 0
    if db_trade_comp != 0:
        team.trade_compensation = db_trade_comp
    if db_faab_adj != 0:
        team.faab_budget = team.faab_budget + db_faab_adj

    team_id = db_team.get("id")
    if team_id:
        db_buyouts = get_team_buyouts(team_id, year)
        for bo in db_buyouts:
            team.buyout_records.append(_build_buyout_record(bo))


def enrich_teams_from_db(ls, db_teams: list[dict], year: int):
    """Apply DB adjustments to all teams in a LeagueState.

    Replaces league.py::_enrich_teams_from_db.
    """
    db_map: dict[str, dict] = {t["manager_name"]: t for t in db_teams}
    for t in ls.teams:
        db_team = db_map.get(t.manager_name)
        if db_team:
            apply_db_adjustments(t, db_team, year)


# ---------------------------------------------------------------------------
# KeeperSelectionResponse list builder (was duplicated 3 times in teams.py)
# ---------------------------------------------------------------------------

def to_selection_responses(selections_db: list[dict]) -> list[KeeperSelectionResponse]:
    """Convert DB selection rows to KeeperSelectionResponse list."""
    return [
        KeeperSelectionResponse(
            player_name=s["player_name"],
            current_contract=s["current_contract"],
            action=s["action"],
            extension_years=s["extension_years"],
            next_contract=s["next_contract"],
        )
        for s in selections_db
    ]


# ---------------------------------------------------------------------------
# Keeper options builder (was duplicated 2 times in teams.py)
# ---------------------------------------------------------------------------

def build_keeper_options(team, *, infer_keep_action, extract_extension_years, serialize_player):
    """Build keeper options for all players on a team.

    Takes callback functions to avoid circular imports with teams.py.
    """
    from src.contract.engine import generate_keeper_options

    result = []
    for player in team.players:
        options = generate_keeper_options(player)
        option_schemas = []
        for opt in options:
            keep_action = infer_keep_action(opt, player)
            ext_years = 0
            if "extend" in keep_action:
                ext_years = extract_extension_years(opt)
                keep_action = "extend"
            option_schemas.append({
                "player_name": opt.player_name,
                "current_contract": opt.current_contract.display,
                "next_contract": opt.next_contract.display if opt.next_contract else None,
                "action": opt.action,
                "salary_change": opt.salary_change,
                "is_mandatory": opt.is_mandatory,
                "keep_action": keep_action,
                "extension_years": ext_years,
            })
        result.append({
            "player": serialize_player(player).model_dump(),
            "options": option_schemas,
            "is_mandatory_keeper": player.is_mandatory_keeper,
        })
    return result
