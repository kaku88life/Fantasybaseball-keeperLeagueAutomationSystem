"""
Update the 2026 league snapshot after the draft is complete.

Merges keeper contracts from 2026_contracts_v2.json with new draft picks
from yahoo_2026_draft.json, using yahoo_2026_rosters.json for latest
positions and MLB teams.

Usage (CLI):
    python -m scripts.update_2026_post_draft

Usage (programmatic, called from FastAPI lifespan):
    from scripts.update_2026_post_draft import run_post_draft_update
    result = run_post_draft_update(verbose=False)
    # result = {"teams": 16, "keepers": 240, "new_draft": 192, ...}
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import FAAB_BASE, get_salary_cap
from src.contract.models import (
    BuyoutRecord,
    Contract,
    ContractType,
    LeagueState,
    Player,
    SpecialStatus,
    Team,
)
from api.database import get_all_keeper_selections, save_snapshot, upsert_team
from api.serializers import league_state_to_dict

CONTRACTS_PATH = ROOT / "data" / "2026_contracts_v2.json"
DRAFT_PATH = ROOT / "data" / "yahoo_2026_draft.json"
ROSTERS_PATH = ROOT / "data" / "yahoo_2026_rosters.json"
BUYOUT_PATH = ROOT / "data" / "2025_buyout_records.json"
STANDINGS_PATH = ROOT / "data" / "2025_playoff_standings.json"
YEAR = 2026

CT_MAP = {v.value: v for v in ContractType}


def norm(name: str) -> str:
    """Normalize player name for matching."""
    name = unicodedata.normalize("NFKC", name)
    return name.lower().strip()


def parse_contract_2026(contract_str: str) -> tuple[str, int, int]:
    """Parse '2026 contract' strings like 'B/$35', '$45/N2', 'EXPIRED'."""
    import re

    if contract_str == "EXPIRED":
        return "O", 0, 0  # will be treated as new draft pick

    # Format: $salary/TypeExt
    m = re.match(r"\$(\d+)/([ABNOR])(\d*)", contract_str)
    if m:
        return m.group(2), int(m.group(1)), int(m.group(3) or 0)

    # Format: Type/$salary
    m = re.match(r"([ABNOR])/\$(\d+)", contract_str)
    if m:
        return m.group(1), int(m.group(2)), 0

    raise ValueError(f"Cannot parse contract: {contract_str}")


def run_post_draft_update(verbose: bool = True) -> dict:
    """Merge 2026 keeper contracts with draft results and save to DB.

    Returns a summary dict: {teams, keepers, new_draft, expired_redraft, year}.
    Safe to call from a running event loop (does not invoke init_db).
    Raises on file/IO errors so callers can log a stack trace.
    """
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # 1. Load existing keeper contracts
    log("Loading keeper contracts...")
    with open(CONTRACTS_PATH, "r", encoding="utf-8") as f:
        contracts_data = json.load(f)

    # Build keeper lookup: normalized_name -> contract info
    keeper_lookup: dict[str, dict] = {}
    for mgr, team_data in contracts_data["teams"].items():
        for p in team_data["players"]:
            keeper_lookup[norm(p["name"])] = {
                "manager": mgr,
                "contract_2026": p.get("contract_2026", ""),
                "contract_2026_type": p.get("contract_2026_type", ""),
                "contract_2026_salary": p.get("contract_2026_salary", 0),
                "contract_2026_ext": p.get("contract_2026_ext", 0),
                "source": p.get("source", ""),
            }

    # 2a. Load 2026 keeper selections from DB — GM actual decisions
    #     (B→N extend, R→activate, release, etc.). These override the default
    #     contract evolution baked into 2026_contracts_v2.json.
    selection_lookup: dict[tuple[str, str], dict] = {}
    try:
        selections = get_all_keeper_selections(year=YEAR)
        for sel in selections:
            key = (norm(sel["manager_name"]), norm(sel["player_name"]))
            selection_lookup[key] = sel
        if selections:
            log(f"Loaded {len(selections)} keeper selections from DB (year={YEAR})")
        else:
            log(f"No {YEAR} keeper selections in DB — using base evolution only")
    except Exception as e:
        log(f"Could not load keeper selections from DB: {e}")

    # 2b. Load draft results
    log("Loading draft results...")
    with open(DRAFT_PATH, "r", encoding="utf-8") as f:
        draft = json.load(f)

    # 3. Load rosters (for latest positions and MLB teams)
    log("Loading rosters...")
    with open(ROSTERS_PATH, "r", encoding="utf-8") as f:
        rosters = json.load(f)

    # Build roster lookup by manager -> player info
    roster_lookup: dict[str, dict[str, dict]] = {}
    manager_team_keys: dict[str, str] = {}
    for team_key, team_info in rosters.items():
        mgr = team_info["manager"]
        manager_team_keys[mgr] = team_key
        roster_lookup[mgr] = {}
        for p in team_info["players"]:
            roster_lookup[mgr][norm(p["name"])] = p

    # 4. Build final 2026 teams
    salary_cap = get_salary_cap(YEAR)
    log(f"\nBuilding 2026 post-draft state (salary cap: ${salary_cap})")
    log("=" * 60)

    # Group draft picks by manager
    from collections import defaultdict
    draft_by_manager: dict[str, list[dict]] = defaultdict(list)
    for d in draft:
        draft_by_manager[d["manager"]].append(d)

    # Load ranking bonus
    ranking_bonus_map: dict[str, int] = {}
    if STANDINGS_PATH.exists():
        with open(STANDINGS_PATH, "r", encoding="utf-8") as f:
            ranking_bonus_map = json.load(f).get("ranking_bonus_map", {})

    teams: list[Team] = []
    total_keepers = 0
    total_new = 0
    total_expired_redraft = 0

    for mgr, picks in sorted(draft_by_manager.items()):
        players: list[Player] = []
        mgr_keepers = 0
        mgr_new = 0

        for d in picks:
            pname = d["player_name"]
            pname_norm = norm(pname)

            # Look up roster info for position/mlb_team
            roster_info = roster_lookup.get(mgr, {}).get(pname_norm, {})
            position = d.get("position", "") or roster_info.get("position", "")
            mlb_team = d.get("mlb_team", "") or roster_info.get("team", "")

            # Check if this is a keeper
            k = keeper_lookup.get(pname_norm)
            sel = selection_lookup.get((norm(mgr), pname_norm))
            # A GM-chosen release/fa overrides whatever v2.json auto-evolution says.
            # Without this, a player released in the keeper deadline but redrafted
            # by the same team would inherit their old B/N/O contract instead of
            # getting a fresh A contract at draft cost.
            released_by_gm = bool(sel) and sel.get("action", "") in (
                "release",
                "release_normal",
                "fa",
            )
            is_keeper = (
                not released_by_gm
                and k is not None
                and k["manager"] == mgr
                and k["contract_2026"] != "EXPIRED"
            )

            if is_keeper:
                # Start from evolved base contract in v2.json
                ct_str = k["contract_2026_type"]
                salary = k["contract_2026_salary"]
                ext = k["contract_2026_ext"]
                source = k["source"]

                # Overlay GM keeper selection if it exists in DB.
                # next_contract examples: "$20/B", "$35/N3", "$1/A" (activate R)
                if sel and sel.get("next_contract"):
                    nc = sel["next_contract"]
                    if "/" in nc:
                        nc_salary_str, nc_type_str = nc.split("/", 1)
                        try:
                            nc_salary = int(nc_salary_str.replace("$", "").strip())
                        except ValueError:
                            nc_salary = salary
                        nc_ext = 0
                        nc_ct = nc_type_str
                        if nc_ct.startswith("N") and len(nc_ct) > 1 and nc_ct[1:].isdigit():
                            nc_ext = int(nc_ct[1:])
                            nc_ct = "N"
                        if nc_ct in CT_MAP:
                            ct_str = nc_ct
                            salary = nc_salary
                            ext = nc_ext
                mgr_keepers += 1
            else:
                # New draft pick or expired player re-drafted -> A contract
                ct_str = "A"
                salary = d["cost"]
                ext = 0
                source = "draft"
                mgr_new += 1
                if k and k["contract_2026"] == "EXPIRED":
                    total_expired_redraft += 1

            ct = CT_MAP.get(ct_str, ContractType.A)
            contract = Contract(
                contract_type=ct,
                salary=salary,
                extension_years=ext,
                special_status=SpecialStatus.NONE,
            )
            player = Player(
                name=pname,
                position=position,
                contract=contract,
                yahoo_player_id=d.get("player_key", ""),
                is_active_keeper=(ct != ContractType.R),
                source=source,
                mlb_team=mlb_team.upper() if mlb_team else "",
            )
            players.append(player)

        team = Team(
            manager_name=mgr,
            team_name="",
            yahoo_team_id=manager_team_keys.get(mgr, ""),
            players=players,
            buyout_records=[],
            salary_cap=salary_cap,
            faab_budget=FAAB_BASE,
            ranking_bonus=ranking_bonus_map.get(mgr, 0),
            trade_compensation=0,
        )
        teams.append(team)

        total_keepers += mgr_keepers
        total_new += mgr_new
        keeper_cost = sum(p.contract.salary for p in players if p.source != "draft")
        draft_cost = sum(p.contract.salary for p in players if p.source == "draft")
        log(f"  {mgr}: {mgr_keepers} keepers + {mgr_new} draft = {len(players)} "
            f"(keeper ${keeper_cost} + draft ${draft_cost} = ${keeper_cost + draft_cost})")

    # Load buyout records
    if BUYOUT_PATH.exists():
        with open(BUYOUT_PATH, "r", encoding="utf-8") as f:
            buyout_data = json.load(f)

        team_lookup = {t.manager_name: t for t in teams}
        loaded = 0
        for br in buyout_data:
            mgr = br["team"]
            team = team_lookup.get(mgr)
            if team:
                remaining = br.get("remaining_years", 1) - 1
                if remaining <= 0:
                    continue
                is_legal = br.get("legal_issue", False)
                team.buyout_records.append(BuyoutRecord(
                    player_name=br["player_name"],
                    original_contract=br["original_contract"],
                    buyout_salary_cost=br["salary_cost"] if not is_legal else 0,
                    buyout_faab_cost=br["faab_cost"] if not is_legal else 0,
                    remaining_years=remaining,
                    use_faab=br["faab_cost"] > 0 and not is_legal,
                    note=br.get("note", ""),
                ))
                loaded += 1
        log(f"\nBuyout records carried over: {loaded}")

    # Save to DB (init_db is expected to have been called by the caller,
    # e.g. FastAPI lifespan or CLI wrapper below).
    ls = LeagueState(year=YEAR, teams=teams)
    ls_dict = league_state_to_dict(ls)

    save_snapshot(year=YEAR, data=ls_dict, source_file="post_draft_2026")
    log(f"\nSaved league snapshot for year {YEAR}")

    for team in teams:
        upsert_team(
            manager_name=team.manager_name,
            team_name=team.team_name,
            yahoo_team_id=team.yahoo_team_id,
        )
    log(f"Upserted {len(teams)} team records")

    # Summary
    log(f"\n{'=' * 60}")
    log(f"Total: {total_keepers} keepers + {total_new} new draft = {total_keepers + total_new}")
    log(f"Expired players re-drafted as new A: {total_expired_redraft}")
    log(f"Salary cap: ${salary_cap}")
    log(f"\nDone! Year {YEAR} snapshot updated with post-draft data.")

    return {
        "year": YEAR,
        "teams": len(teams),
        "keepers": total_keepers,
        "new_draft": total_new,
        "expired_redraft": total_expired_redraft,
        "salary_cap": salary_cap,
    }


if __name__ == "__main__":
    # CLI entry point: init DB explicitly, then run the update.
    import asyncio
    from api.database import init_db

    asyncio.run(init_db())
    run_post_draft_update(verbose=True)
