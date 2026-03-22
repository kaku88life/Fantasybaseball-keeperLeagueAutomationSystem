"""
Update the 2026 league snapshot after the draft is complete.

Merges keeper contracts from 2026_contracts_v2.json with new draft picks
from yahoo_2026_draft.json, using yahoo_2026_rosters.json for latest
positions and MLB teams.

Usage:
    python -m scripts.update_2026_post_draft
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
from api.database import init_db, save_snapshot, upsert_team
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


def main():
    # 1. Load existing keeper contracts
    print("Loading keeper contracts...")
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

    # 2. Load draft results
    print("Loading draft results...")
    with open(DRAFT_PATH, "r", encoding="utf-8") as f:
        draft = json.load(f)

    # 3. Load rosters (for latest positions and MLB teams)
    print("Loading rosters...")
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
    print(f"\nBuilding 2026 post-draft state (salary cap: ${salary_cap})")
    print("=" * 60)

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
            is_keeper = (
                k is not None
                and k["manager"] == mgr
                and k["contract_2026"] != "EXPIRED"
            )

            if is_keeper:
                # Use evolved 2026 contract
                ct_str = k["contract_2026_type"]
                salary = k["contract_2026_salary"]
                ext = k["contract_2026_ext"]
                source = k["source"]
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
                is_active_keeper=True,
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
        print(f"  {mgr}: {mgr_keepers} keepers + {mgr_new} draft = {len(players)} "
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
        print(f"\nBuyout records carried over: {loaded}")

    # Save to DB
    ls = LeagueState(year=YEAR, teams=teams)
    ls_dict = league_state_to_dict(ls)

    import asyncio
    asyncio.run(init_db())

    save_snapshot(year=YEAR, data=ls_dict, source_file="post_draft_2026")
    print(f"\nSaved league snapshot for year {YEAR}")

    for team in teams:
        upsert_team(
            manager_name=team.manager_name,
            team_name=team.team_name,
            yahoo_team_id=team.yahoo_team_id,
        )
    print(f"Upserted {len(teams)} team records")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Total: {total_keepers} keepers + {total_new} new draft = {total_keepers + total_new}")
    print(f"Expired players re-drafted as new A: {total_expired_redraft}")
    print(f"Salary cap: ${salary_cap}")
    print(f"\nDone! Year {YEAR} snapshot updated with post-draft data.")


if __name__ == "__main__":
    main()
