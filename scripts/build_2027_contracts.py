"""
Build 2027 contract projections from the 2026 post-draft state.

Evolves all 2026 contracts to 2027 according to league rules:
  A -> B (salary unchanged)
  B -> O (salary unchanged, expiring year)
  N(x) -> N(x-1) when x > 1
  N(1) -> O
  O -> EXPIRED (free agent)
  R -> R (farm rookie, unchanged)
  Draft (A) -> B next year

Produces data/2027_contracts_v1.json and loads into DB as year=2027.

Usage:
    python -m scripts.build_2027_contracts
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
    Contract,
    ContractType,
    LeagueState,
    Player,
    SpecialStatus,
    Team,
)
from api.database import init_db, save_snapshot, upsert_team
from api.serializers import league_state_to_dict

DRAFT_PATH = ROOT / "data" / "yahoo_2026_draft.json"
CONTRACTS_PATH = ROOT / "data" / "2026_contracts_v2.json"
ROSTERS_PATH = ROOT / "data" / "yahoo_2026_rosters.json"
OUTPUT_PATH = ROOT / "data" / "2027_contracts_v1.json"
STANDINGS_PATH = ROOT / "data" / "2025_playoff_standings.json"
YEAR = 2027

CT_MAP = {v.value: v for v in ContractType}


def norm(name: str) -> str:
    return unicodedata.normalize("NFKC", name).lower().strip()


def evolve_contract(ct: str, salary: int, ext: int) -> tuple[str, int, int, bool]:
    """Evolve a 2026 contract to its 2027 state.

    Returns (new_type, new_salary, new_ext, is_expired).
    Salary is unchanged in all evolution steps (per league rules).
    """
    if ct == "A":
        return "B", salary, 0, False
    elif ct == "B":
        return "O", salary, 0, False
    elif ct == "N":
        if ext > 1:
            return "N", salary, ext - 1, False
        else:
            # N(1) -> O
            return "O", salary, 0, False
    elif ct == "O":
        return "O", 0, 0, True  # EXPIRED
    elif ct == "R":
        return "R", salary, 0, False
    else:
        return "A", salary, 0, False


def main():
    # 1. Load 2026 keeper contracts + draft results to build complete 2026 state
    print("Loading 2026 contracts...")
    with open(CONTRACTS_PATH, "r", encoding="utf-8") as f:
        contracts_data = json.load(f)

    print("Loading 2026 draft...")
    with open(DRAFT_PATH, "r", encoding="utf-8") as f:
        draft = json.load(f)

    print("Loading 2026 rosters...")
    with open(ROSTERS_PATH, "r", encoding="utf-8") as f:
        rosters = json.load(f)

    # Build keeper lookup
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

    # Build roster info
    roster_lookup: dict[str, dict[str, dict]] = {}
    manager_team_keys: dict[str, str] = {}
    for team_key, team_info in rosters.items():
        mgr = team_info["manager"]
        manager_team_keys[mgr] = team_key
        roster_lookup[mgr] = {}
        for p in team_info["players"]:
            roster_lookup[mgr][norm(p["name"])] = p

    # 2. Build 2026 state and evolve to 2027
    from collections import defaultdict
    draft_by_manager: defaultdict[str, list[dict]] = defaultdict(list)
    for d in draft:
        draft_by_manager[d["manager"]].append(d)

    salary_cap = get_salary_cap(YEAR)
    print(f"\nBuilding 2027 contracts (salary cap: ${salary_cap})")
    print("=" * 60)

    output_teams: dict[str, dict] = {}
    teams: list[Team] = []
    total_kept = 0
    total_expired = 0

    for mgr, picks in sorted(draft_by_manager.items()):
        players_2027: list[dict] = []
        model_players: list[Player] = []
        mgr_kept = 0
        mgr_expired = 0

        for d in picks:
            pname = d["player_name"]
            pname_norm = norm(pname)
            roster_info = roster_lookup.get(mgr, {}).get(pname_norm, {})
            position = d.get("position", "") or roster_info.get("position", "")
            mlb_team = (d.get("mlb_team", "") or roster_info.get("team", "")).upper()

            # Determine 2026 contract
            k = keeper_lookup.get(pname_norm)
            is_keeper = (
                k is not None
                and k["manager"] == mgr
                and k["contract_2026"] != "EXPIRED"
            )

            if is_keeper:
                ct_2026 = k["contract_2026_type"]
                salary_2026 = k["contract_2026_salary"]
                ext_2026 = k["contract_2026_ext"]
                source = k["source"]
            else:
                ct_2026 = "A"
                salary_2026 = d["cost"]
                ext_2026 = 0
                source = "draft"

            # Evolve to 2027
            ct_2027, salary_2027, ext_2027, is_expired = evolve_contract(
                ct_2026, salary_2026, ext_2026
            )

            if is_expired:
                mgr_expired += 1
                contract_2027_str = "EXPIRED"
                can_keep = False
            else:
                mgr_kept += 1
                ext_str = str(ext_2027) if ext_2027 > 0 else ""
                contract_2027_str = f"${salary_2027}/{ct_2027}{ext_str}"
                can_keep = ct_2027 != "O" or True  # O can still be on roster

            # JSON record
            players_2027.append({
                "name": pname,
                "player_key": d.get("player_key", ""),
                "position": position,
                "mlb_team": mlb_team,
                "source": source,
                "contract_2026": f"${salary_2026}/{ct_2026}{ext_2026 if ext_2026 else ''}",
                "contract_2026_type": ct_2026,
                "contract_2026_salary": salary_2026,
                "contract_2027_type": ct_2027,
                "contract_2027_salary": salary_2027,
                "contract_2027_ext": ext_2027,
                "contract_2027": contract_2027_str,
                "can_keep": ct_2027 != "O",
            })

            # Model for DB
            ct_enum = CT_MAP.get(ct_2027, ContractType.A)
            contract = Contract(
                contract_type=ct_enum,
                salary=salary_2027,
                extension_years=ext_2027,
                special_status=SpecialStatus.NONE,
            )
            model_players.append(Player(
                name=pname,
                position=position,
                contract=contract,
                yahoo_player_id=d.get("player_key", ""),
                is_active_keeper=not is_expired,
                source=source,
                mlb_team=mlb_team,
            ))

        output_teams[mgr] = {
            "team_key": manager_team_keys.get(mgr, ""),
            "players": players_2027,
        }

        team = Team(
            manager_name=mgr,
            team_name="",
            yahoo_team_id=manager_team_keys.get(mgr, ""),
            players=model_players,
            buyout_records=[],
            salary_cap=salary_cap,
            faab_budget=FAAB_BASE,
            ranking_bonus=0,  # 2026 season hasn't happened yet
            trade_compensation=0,
        )
        teams.append(team)

        total_kept += mgr_kept
        total_expired += mgr_expired
        print(f"  {mgr}: {mgr_kept} keepable + {mgr_expired} expired = {len(picks)}")

    # 3. Save JSON
    output = {
        "year": YEAR,
        "source": "auto_evolved_from_2026",
        "teams": output_teams,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {OUTPUT_PATH.name}")

    # 4. Save to DB
    ls = LeagueState(year=YEAR, teams=teams)
    ls_dict = league_state_to_dict(ls)

    try:
        import asyncio
        asyncio.run(init_db())
        save_snapshot(year=YEAR, data=ls_dict, source_file="2027_contracts_v1.json")
        print(f"Saved league snapshot for year {YEAR}")

        for team in teams:
            upsert_team(
                manager_name=team.manager_name,
                team_name=team.team_name,
                yahoo_team_id=team.yahoo_team_id,
            )
        print(f"Upserted {len(teams)} team records")
    except Exception as e:
        print(f"DB save skipped (not connected): {e}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"2027 projections: {total_kept} keepable + {total_expired} expired")
    print(f"Salary cap: ${salary_cap}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
