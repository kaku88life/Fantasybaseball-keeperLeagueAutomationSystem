"""
Build 2027 season snapshot from Yahoo 2026 roster + 2026 keeper contracts.

Logic:
  1. Start from Yahoo 2026 season roster (yahoo_2026_rosters.json, 27~33 players/team)
  2. Cross-reference with 2026 keepers (2026_contracts_v2.json) for base contract types
  3. Apply 2026 keeper_selections from DB (if submitted):
     - keep: A->B, B->O, R->R (reflected in next_contract)
     - activate: R->A
     - extend: B->N(x), salary += x*$5
     - release/fa: marked as FA
  4. If no keeper_selections exist for a team, use base contract as-is
  5. Players NOT in keeper list -> acquired in 2026 draft or FAAB -> A contract
  6. ALL players are included (including O/FA contracts)

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
from api.database import init_db, save_snapshot, upsert_team, get_all_keeper_selections, get_synced_roster
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


def main():
    # 1. Load data sources
    print("Loading 2026 keeper contracts...")
    with open(CONTRACTS_PATH, "r", encoding="utf-8") as f:
        contracts_data = json.load(f)

    print("Loading 2026 draft results...")
    with open(DRAFT_PATH, "r", encoding="utf-8") as f:
        draft = json.load(f)

    # Load rosters: prefer DB synced version (persists across deployments),
    # fall back to local file, then draft data as last resort.
    rosters = None
    try:
        db_rosters = get_synced_roster(2026)
        if db_rosters:
            total_db_players = sum(
                len(t.get("players", []) if isinstance(t, dict) else [])
                for t in db_rosters.values()
            )
            if total_db_players > 0:
                rosters = db_rosters
                print(f"Loaded Yahoo 2026 rosters from DB ({len(rosters)} teams, {total_db_players} players)")
    except Exception as e:
        print(f"Could not load synced roster from DB: {e}")

    if rosters is None:
        print("Loading Yahoo 2026 rosters from file...")
        with open(ROSTERS_PATH, "r", encoding="utf-8") as f:
            rosters = json.load(f)

    # Validate roster data: must have teams with players
    total_roster_players = sum(
        len(t.get("players", []) if isinstance(t, dict) else [])
        for t in rosters.values()
    )
    if total_roster_players == 0:
        print("[WARNING] Roster data has 0 players!")
        print("  Falling back to draft data as roster source...")
        rosters = {}
        for d in draft:
            mgr = d["manager"]
            matched_key = None
            for tk, ti in rosters.items():
                if ti["manager"] == mgr:
                    matched_key = tk
                    break
            if not matched_key:
                matched_key = d.get("team_key", f"fallback.{mgr}")
                rosters[matched_key] = {"manager": mgr, "team_name": "", "players": []}
            rosters[matched_key]["players"].append({
                "name": d["player_name"],
                "player_key": d.get("player_key", ""),
                "position": d.get("position", ""),
                "team": d.get("mlb_team", ""),
                "selected_position": "",
                "status": "",
            })
        print(f"  Rebuilt {len(rosters)} teams from draft data")

    # 2. Build keeper lookup: manager_norm -> player_norm -> contract info
    #    These are pre-2026 keepers (players carried over into 2026 season)
    keeper_lookup: dict[str, dict[str, dict]] = {}
    for mgr, team_data in contracts_data["teams"].items():
        mgr_norm = norm(mgr)
        keeper_lookup[mgr_norm] = {}
        for p in team_data["players"]:
            keeper_lookup[mgr_norm][norm(p["name"])] = {
                "contract_type": p.get("contract_2026_type") or "A",
                "salary": p.get("contract_2026_salary") or 0,
                "ext": p.get("contract_2026_ext") or 0,
                "source": p.get("source", "keeper"),
                "contract_display": p.get("contract_2026", ""),
            }

    # 3. Build draft lookup: (manager_norm, player_norm) -> draft info
    draft_lookup: dict[tuple[str, str], dict] = {}
    for d in draft:
        draft_lookup[(norm(d["manager"]), norm(d["player_name"]))] = d

    # 4. Load 2026 keeper selections from DB (actual GM decisions)
    #    These reflect activate/extend/keep/release choices made by each GM.
    #    Only applied when selections exist; otherwise fall back to base contract.
    selection_lookup: dict[tuple[str, str], dict] = {}
    try:
        selections = get_all_keeper_selections(year=2026)
        for sel in selections:
            key = (norm(sel["manager_name"]), norm(sel["player_name"]))
            selection_lookup[key] = sel
        if selections:
            print(f"Loaded {len(selections)} keeper selections from DB (2026)")
        else:
            print("No 2026 keeper selections found in DB (will use base contracts)")
    except Exception as e:
        print(f"Could not load keeper selections from DB: {e}")
        print("  Using base contracts without evolution")

    salary_cap = get_salary_cap(YEAR)
    print(f"\nBuilding 2027 snapshot (salary cap: ${salary_cap})")
    print("=" * 60)

    output_teams: dict[str, dict] = {}
    teams: list[Team] = []
    total_keeper = 0
    total_draft = 0
    total_faab = 0

    # 5. Iterate Yahoo rosters (the actual 2026 season roster, 27~33 players/team)
    for team_key, team_info in sorted(rosters.items(), key=lambda x: x[1]["manager"]):
        mgr = team_info["manager"]
        mgr_norm = norm(mgr)
        team_name = team_info.get("team_name", "")
        mgr_keepers = keeper_lookup.get(mgr_norm, {})

        players_out: list[dict] = []
        model_players: list[Player] = []
        mgr_keeper_count = 0
        mgr_draft_count = 0
        mgr_faab_count = 0

        for rp in team_info["players"]:
            pname = rp["name"]
            pname_norm = norm(pname)
            position = rp.get("position", "")
            mlb_team = rp.get("team", "").upper()
            player_key = rp.get("player_key", "")

            # Check 1: Is this player in the 2026 keepers list?
            k = mgr_keepers.get(pname_norm)
            if k is not None:
                # Start with base 2026 contract
                ct = k["contract_type"]
                salary = k["salary"]
                ext = k["ext"]
                source = k["source"]

                # Apply keeper selection if exists (evolve contract based on GM choice)
                sel = selection_lookup.get((mgr_norm, pname_norm))
                if sel and sel.get("next_contract"):
                    nc = sel["next_contract"]  # e.g. "$14/B", "$1/A", "$35/N3"
                    # Parse next_contract: "$salary/type[ext]"
                    if "/" in nc:
                        nc_salary_str, nc_type_str = nc.split("/", 1)
                        nc_salary = int(nc_salary_str.replace("$", "").strip())
                        # Extract contract type and extension years (e.g. "N3" -> "N", 3)
                        nc_ext = 0
                        nc_ct = nc_type_str
                        if nc_ct.startswith("N") and len(nc_ct) > 1 and nc_ct[1:].isdigit():
                            nc_ext = int(nc_ct[1:])
                            nc_ct = "N"
                        # Apply evolved contract
                        ct = nc_ct
                        salary = nc_salary
                        ext = nc_ext

                    # If action is release/fa, player is gone but still on Yahoo roster
                    action = sel.get("action", "")
                    if action in ("release", "release_normal", "fa"):
                        ct = "FA"
                        salary = 0
                        ext = 0
                        source = "released"

                mgr_keeper_count += 1
            else:
                # Check 2: Is this player in the 2026 draft?
                d = draft_lookup.get((mgr_norm, pname_norm))
                if d is not None:
                    ct = "A"
                    salary = d["cost"]
                    ext = 0
                    source = "draft"
                    # Use draft data for position/team if roster data is missing
                    position = position or d.get("position", "")
                    mlb_team = mlb_team or (d.get("mlb_team", "")).upper()
                    player_key = player_key or d.get("player_key", "")
                    mgr_draft_count += 1
                else:
                    # Not in keepers or draft -> FAAB pickup during 2026 season
                    ct = "A"
                    salary = 1  # FAAB minimum bid
                    ext = 0
                    source = "faab"
                    mgr_faab_count += 1

            ext_str = str(ext) if ext > 0 else ""
            contract_display = f"${salary}/{ct}{ext_str}"

            # JSON record
            players_out.append({
                "name": pname,
                "player_key": player_key,
                "position": position,
                "mlb_team": mlb_team,
                "source": source,
                "contract_type": ct,
                "salary": salary,
                "extension_years": ext,
                "contract_display": contract_display,
            })

            # Model for DB snapshot
            ct_enum = CT_MAP.get(ct, ContractType.A)
            contract = Contract(
                contract_type=ct_enum,
                salary=salary,
                extension_years=ext,
                special_status=SpecialStatus.NONE,
            )
            model_players.append(Player(
                name=pname,
                position=position,
                contract=contract,
                yahoo_player_id=player_key,
                is_active_keeper=(ct_enum != ContractType.R),
                source=source,
                mlb_team=mlb_team,
            ))

        output_teams[mgr] = {
            "team_key": team_key,
            "players": players_out,
        }

        team = Team(
            manager_name=mgr,
            team_name=team_name,
            yahoo_team_id=team_key,
            players=model_players,
            buyout_records=[],
            salary_cap=salary_cap,
            faab_budget=FAAB_BASE,
            ranking_bonus=0,  # 2026 season hasn't ended yet
            trade_compensation=0,
        )
        teams.append(team)

        total_keeper += mgr_keeper_count
        total_draft += mgr_draft_count
        total_faab += mgr_faab_count
        print(
            f"  {mgr:20s} {len(team_info['players']):3d} players "
            f"(keeper:{mgr_keeper_count} draft:{mgr_draft_count} faab:{mgr_faab_count})"
        )

    # 5. Save JSON
    output = {
        "year": YEAR,
        "source": "yahoo_2026_roster_with_contracts",
        "teams": output_teams,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {OUTPUT_PATH.name}")

    # 6. Save to DB
    ls = LeagueState(year=YEAR, teams=teams)
    ls_dict = league_state_to_dict(ls)

    try:
        import asyncio
        # init_db is async — handle both standalone and scheduler contexts
        try:
            loop = asyncio.get_running_loop()
            # Already in an event loop (e.g. scheduler context) — skip async init
            # DB tables should already exist from startup lifespan
        except RuntimeError:
            # No running loop (standalone script) — safe to use asyncio.run
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
    print(f"Total: {total_keeper} keepers + {total_draft} draft + {total_faab} faab")
    print(f"Teams: {len(teams)} | Salary cap: ${salary_cap}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
