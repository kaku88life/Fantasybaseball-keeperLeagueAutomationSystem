"""
Load 2026 contract data from JSON into the database.

Reads data/2026_contracts_v2.json, builds LeagueState with 2025 contracts
(so the contract engine can compute 2026 keeper options dynamically),
and saves to league_snapshots + teams tables.

Usage:
    python -m scripts.load_2026_contracts
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Add project root to path
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

JSON_PATH = ROOT / "data" / "2026_contracts_v2.json"
BUYOUT_PATH = ROOT / "data" / "2025_buyout_records.json"
STANDINGS_PATH = ROOT / "data" / "2025_playoff_standings.json"
YEAR = 2026

CT_MAP = {v.value: v for v in ContractType}


def parse_contract_string(contract_str: str) -> tuple[str, int, int]:
    """Parse contract string like '$12/N1', '$3/B', 'A/$5', '$1/R'.

    Returns (contract_type, salary, extension_years).
    """
    # Format: $salary/TypeExt  (e.g. $12/N1, $3/B, $58/O, $1/R)
    m = re.match(r"\$(\d+)/([ABNOR])(\d*)", contract_str)
    if m:
        return m.group(2), int(m.group(1)), int(m.group(3) or 0)

    # Format: Type/$salary  (e.g. A/$5, B/$10)
    m = re.match(r"([ABNOR])/\$(\d+)", contract_str)
    if m:
        return m.group(1), int(m.group(2)), 0

    raise ValueError(f"Cannot parse contract string: {contract_str}")


def build_player(player_data: dict) -> Player:
    """Convert a JSON player record to a Player model with 2025 contract."""
    ct_str = player_data.get("contract_type")

    if ct_str is None:
        # trade_keeper players are missing contract_type/salary/extension_years
        # Parse from the contract_2025 string instead
        ct_str, salary, ext = parse_contract_string(player_data["contract_2025"])
    else:
        salary = player_data["salary"]
        ext = player_data.get("extension_years", 0)

    resolved_type = CT_MAP.get(ct_str, ContractType.A)

    contract = Contract(
        contract_type=resolved_type,
        salary=salary,
        extension_years=ext,
        special_status=SpecialStatus.NONE,
    )

    return Player(
        name=player_data["name"],
        position=player_data.get("position", ""),
        contract=contract,
        yahoo_player_id=player_data.get("player_key"),
        is_active_keeper=True,
        source=player_data.get("source", ""),
    )


def load_contracts():
    """Main function: load JSON and populate database."""
    if not JSON_PATH.exists():
        print(f"Error: {JSON_PATH} not found")
        sys.exit(1)

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    salary_cap = get_salary_cap(YEAR)
    print(f"Loading 2026 contracts (salary cap: ${salary_cap})")
    print(f"Source: {JSON_PATH}")
    print()

    # Load 2025 playoff standings for ranking bonus
    ranking_bonus_map: dict[str, int] = {}
    if STANDINGS_PATH.exists():
        with open(STANDINGS_PATH, "r", encoding="utf-8") as f:
            standings_data = json.load(f)
        ranking_bonus_map = standings_data.get("ranking_bonus_map", {})
        print(f"Loaded ranking bonus from {STANDINGS_PATH.name}:")
        for mgr, bonus in ranking_bonus_map.items():
            if bonus > 0:
                print(f"  {mgr}: +${bonus}")
        print()
    else:
        print(f"WARNING: {STANDINGS_PATH} not found, all ranking_bonus = 0\n")

    teams_data = data.get("teams", {})
    teams: list[Team] = []
    total_players = 0
    total_keepable = 0

    for manager_name, team_data in teams_data.items():
        players: list[Player] = []
        team_keepable = 0

        for pd in team_data.get("players", []):
            player = build_player(pd)
            players.append(player)
            if player.contract.is_keepable:
                team_keepable += 1

        team = Team(
            manager_name=manager_name,
            team_name="",
            yahoo_team_id=team_data.get("team_key", ""),
            players=players,
            buyout_records=[],
            salary_cap=salary_cap,
            faab_budget=FAAB_BASE,
            ranking_bonus=ranking_bonus_map.get(manager_name, 0),
            trade_compensation=0,
        )
        teams.append(team)

        total_players += len(players)
        total_keepable += team_keepable
        print(f"  {manager_name}: {len(players)} players ({team_keepable} keepable)")

    # Load 2025 buyout records — only carry over records with remaining obligation
    # Buyouts executed in 2025 with remaining_years=1 are fully paid; skip them.
    # Multi-year buyouts (remaining_years > 1) still have obligation; carry over
    # with remaining_years decremented by 1.
    if BUYOUT_PATH.exists():
        with open(BUYOUT_PATH, "r", encoding="utf-8") as f:
            buyout_data = json.load(f)

        team_lookup = {t.manager_name: t for t in teams}
        loaded_count = 0
        skipped_count = 0

        for br in buyout_data:
            mgr = br["team"]
            team = team_lookup.get(mgr)
            if team:
                is_legal_issue = br.get("legal_issue", False)
                remaining = br.get("remaining_years", 1)

                # Buyout was executed in 2025; one year of obligation consumed.
                # If remaining_years was 1, the obligation is fully paid — skip.
                remaining_after = remaining - 1
                if remaining_after <= 0:
                    skipped_count += 1
                    continue

                # Multi-year buyout still has obligation remaining
                team.buyout_records.append(BuyoutRecord(
                    player_name=br["player_name"],
                    original_contract=br["original_contract"],
                    buyout_salary_cost=br["salary_cost"] if not is_legal_issue else 0,
                    buyout_faab_cost=br["faab_cost"] if not is_legal_issue else 0,
                    remaining_years=remaining_after,
                    use_faab=br["faab_cost"] > 0 and not is_legal_issue,
                    note=br.get("note", ""),
                ))
                loaded_count += 1
            else:
                print(f"  WARNING: Buyout team '{mgr}' not found in contracts")

        print(f"\n2025 buyout records: {loaded_count} carried over, {skipped_count} completed (skipped)")
        for t in teams:
            if t.buyout_records:
                total_sal = sum(b.buyout_salary_cost for b in t.buyout_records)
                total_faab = sum(b.buyout_faab_cost for b in t.buyout_records)
                print(f"  {t.manager_name}: {len(t.buyout_records)} ongoing buyouts (salary: ${total_sal}, FAAB: ${total_faab})")
    else:
        print(f"\nNo buyout records file found at {BUYOUT_PATH}")

    # Build LeagueState (year=2026, but contracts are 2025 state)
    # The engine will compute 2026 transitions via generate_keeper_options()
    ls = LeagueState(year=YEAR, teams=teams)
    ls_dict = league_state_to_dict(ls)

    # Initialize DB and save
    import asyncio
    asyncio.run(init_db())

    # Save league snapshot
    save_snapshot(year=YEAR, data=ls_dict, source_file="2026_contracts_v2.json")
    print(f"\nSaved league snapshot for year {YEAR}")

    # Create/update team records in teams table
    for team in teams:
        upsert_team(
            manager_name=team.manager_name,
            team_name=team.team_name,
            yahoo_team_id=team.yahoo_team_id,
        )
    print(f"Upserted {len(teams)} team records")

    # Summary
    print(f"\n{'='*50}")
    print(f"Total: {total_players} players across {len(teams)} teams")
    print(f"Keepable: {total_keepable}, Expired (O): {total_players - total_keepable}")
    print(f"Salary cap: ${salary_cap}, FAAB: ${FAAB_BASE}")
    print(f"DB: {ROOT / 'data' / 'keeper_league.db'}")
    print(f"\nDone! API endpoints should now work for year {YEAR}.")


if __name__ == "__main__":
    load_contracts()
