"""
Comprehensive contract verification for 2025 end-of-season rosters.

Checks:
1. Draft players: verify current team matches drafting team
   - If different team: should be FAAB price, not draft price
2. Keeper players: verify they weren't dropped and re-acquired
   - Same team re-pickup: maintain original contract
   - Different team: new A contract with FAAB price
3. All FAAB players: check if any had prior contracts from other teams
"""
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import openpyxl
from scripts.import_excel import import_yearly_sheet
from src.api.yahoo_client import YahooFantasyClient


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    name = name.replace(".", "").replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name


# Yahoo manager -> Yahoo team_key (2025 league)
YAHOO_MGR_TO_TEAM_KEY = {
    "Ｋａｋｕ": "458.l.40288.t.1",
    "Leo": "458.l.40288.t.16",
    "叫我寬哥": "458.l.40288.t.2",
    "EDDIE": "458.l.40288.t.3",
    "wei": "458.l.40288.t.4",
    "Tony": "458.l.40288.t.5",
    "rawstuff": "458.l.40288.t.6",
    "Billy": "458.l.40288.t.7",
    "YWC": "458.l.40288.t.8",
    "哈寶好": "458.l.40288.t.9",
    "小喆": "458.l.40288.t.10",
    "Hyper": "458.l.40288.t.11",
    "TIMMY LIU": "458.l.40288.t.12",
    "謙謙": "458.l.40288.t.13",
    "魚魚": "458.l.40288.t.14",
    "Ponpon": "458.l.40288.t.15",
}

YAHOO_MGR_TO_EXCEL = {
    "Ｋａｋｕ": "郭子睿(Rangers)",
    "叫我寬哥": "Hank",
    "EDDIE": "Eddie Chen",
    "wei": "Chih-Wei",
    "Tony": "Tony林芳民",
    "rawstuff": "Issac",
    "Billy": "Billy WU",
    "YWC": "ywchiou",
    "哈寶好": "楊善合",
    "小喆": "Yu-Che Chang",
    "Hyper": "林剛",
    "TIMMY LIU": "TIMMY LIU",
    "謙謙": "Javier",
    "魚魚": "James Chen",
    "Ponpon": "Ponpon",
    "Leo": "Leo",
}


def main():
    # Load all data
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        yahoo_rosters = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
        matched_data = json.load(f)

    player_history = tx_data["player_history"]

    # Load Excel contracts (all teams)
    excel_path = r"C:\Users\amy41\OneDrive\Desktop\Baseball\5-Man Keep盟 新版球員名單.xlsx"
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["2025年選秀前名單"]
    teams_2025 = import_yearly_sheet(ws, 2025)

    # Excel contracts by normalized name -> {manager, contract info}
    excel_all = {}
    for team in teams_2025:
        for player in team.players:
            key = normalize_name(player.name)
            excel_all[key] = {
                "name": player.name,
                "manager": team.manager_name,
                "contract_type": player.contract.contract_type.value,
                "salary": player.contract.salary,
                "extension_years": player.contract.extension_years,
                "contract_str": f"${player.contract.salary}/{player.contract.contract_type.value}"
                    + (str(player.contract.extension_years) if player.contract.extension_years else ""),
            }

    # Draft lookup: player_key -> draft info
    draft_by_key = {}
    for d in draft_data:
        draft_by_key[d["player_key"]] = d

    # Build team_key -> yahoo_mgr mapping
    team_key_to_mgr = {}
    for mgr, tk in YAHOO_MGR_TO_TEAM_KEY.items():
        team_key_to_mgr[tk] = mgr

    issues = []

    print("=" * 70)
    print("CHECK 1: Draft players on different teams than who drafted them")
    print("=" * 70)

    for yahoo_mgr, team_data in matched_data.items():
        current_team_key = YAHOO_MGR_TO_TEAM_KEY.get(yahoo_mgr, "")
        for p in team_data.get("draft_new", []):
            player_name = p["name"]
            # Find player_key
            player_key = _find_player_key(yahoo_rosters, yahoo_mgr, player_name)
            if not player_key:
                continue

            draft_info = draft_by_key.get(player_key)
            if not draft_info:
                continue

            original_team_key = draft_info["team_key"]
            if original_team_key != current_team_key:
                original_mgr = team_key_to_mgr.get(original_team_key, original_team_key)
                # Find FAAB cost from transaction history
                faab_cost = _find_faab_cost(player_history, player_key, current_team_key)

                issue = {
                    "type": "draft_wrong_team",
                    "player": player_name,
                    "current_team": yahoo_mgr,
                    "drafted_by": original_mgr,
                    "draft_cost": draft_info["cost"],
                    "faab_cost": faab_cost,
                }
                issues.append(issue)
                print(f"  {player_name:30s} | drafted by {original_mgr:10s} (${draft_info['cost']}) "
                      f"| now on {yahoo_mgr:10s} (FAAB ${faab_cost})")

    if not issues:
        print("  (none found)")

    print()
    print("=" * 70)
    print("CHECK 2: Keeper players dropped and re-acquired")
    print("=" * 70)

    keeper_issues = []
    for yahoo_mgr, team_data in matched_data.items():
        current_team_key = YAHOO_MGR_TO_TEAM_KEY.get(yahoo_mgr, "")
        excel_mgr = YAHOO_MGR_TO_EXCEL.get(yahoo_mgr, yahoo_mgr)

        for p in team_data.get("matched", []):
            player_name = p["name"]
            player_key = _find_player_key(yahoo_rosters, yahoo_mgr, player_name)
            if not player_key or player_key not in player_history:
                continue

            history = player_history[player_key]
            # Check if this player was dropped and re-added during the season
            drops = [e for e in history if e["transaction_type"] == "drop"
                     and e["source_team_key"] == current_team_key]
            adds = [e for e in history if e["transaction_type"] == "add"
                    and e["destination_team_key"] == current_team_key]

            if drops and adds:
                # Player was dropped and re-acquired by the same team
                faab_cost = None
                for a in adds:
                    if a["faab_bid"] is not None:
                        faab_cost = a["faab_bid"]
                issue = {
                    "type": "keeper_dropped_readded",
                    "player": player_name,
                    "team": yahoo_mgr,
                    "original_contract": p["contract_str"],
                    "faab_cost": faab_cost,
                    "action": "MAINTAIN_CONTRACT (same team re-pickup)",
                }
                keeper_issues.append(issue)
                print(f"  {player_name:30s} | {yahoo_mgr:10s} | "
                      f"Contract: {p['contract_str']:>10s} | "
                      f"Dropped & re-added (FAAB ${faab_cost}) -> maintain contract")

    if not keeper_issues:
        print("  (none found)")

    print()
    print("=" * 70)
    print("CHECK 3: Keeper players that moved to different teams")
    print("=" * 70)

    # Check "dropped" players from each team - are any now on another team?
    moved_keepers = []
    for yahoo_mgr, team_data in matched_data.items():
        for p in team_data.get("dropped", []):
            player_name = p["name"]
            norm = normalize_name(player_name)
            # Is this player now on ANY other team's roster?
            for other_mgr, other_data in matched_data.items():
                if other_mgr == yahoo_mgr:
                    continue
                # Check all categories on other team
                for cat in ["no_contract", "draft_new"]:
                    for op in other_data.get(cat, []):
                        if normalize_name(op["name"]) == norm:
                            faab_cost = None
                            pk = _find_player_key(yahoo_rosters, other_mgr, op["name"])
                            if pk and pk in player_history:
                                adds = [e for e in player_history[pk]
                                        if e["transaction_type"] == "add"]
                                if adds:
                                    faab_cost = adds[-1].get("faab_bid")

                            issue = {
                                "type": "keeper_moved_team",
                                "player": player_name,
                                "original_team": yahoo_mgr,
                                "original_contract": p["contract_str"],
                                "new_team": other_mgr,
                                "faab_cost": faab_cost,
                                "current_category": cat,
                            }
                            moved_keepers.append(issue)
                            print(f"  {player_name:30s} | "
                                  f"Was: {yahoo_mgr:10s} ({p['contract_str']}) | "
                                  f"Now: {other_mgr:10s} (cat: {cat}, FAAB ${faab_cost})")

    if not moved_keepers:
        print("  (none found)")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Draft players on wrong team:   {len(issues)}")
    print(f"  Keeper dropped & re-added:     {len(keeper_issues)}")
    print(f"  Keeper moved to other team:    {len(moved_keepers)}")

    total_fixes = len(issues) + len(keeper_issues) + len(moved_keepers)
    if total_fixes > 0:
        print(f"\n  ** {total_fixes} contract(s) need correction **")
    else:
        print(f"\n  All contracts verified correctly!")

    # Save
    result = {
        "draft_wrong_team": issues,
        "keeper_dropped_readded": keeper_issues,
        "keeper_moved_team": moved_keepers,
    }
    with open("data/contract_verification.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved to data/contract_verification.json")


def _find_player_key(yahoo_rosters, yahoo_mgr, player_name):
    """Find a player's key from Yahoo roster data."""
    for tk, td in yahoo_rosters.items():
        if td["manager"] == yahoo_mgr:
            for yp in td["players"]:
                if yp["name"] == player_name:
                    return yp.get("player_key", "")
    return None


def _find_faab_cost(player_history, player_key, target_team_key):
    """Find the FAAB cost for a player's acquisition by a specific team."""
    if player_key not in player_history:
        return 0
    history = player_history[player_key]
    for event in reversed(history):
        if (event["transaction_type"] == "add"
                and event["destination_team_key"] == target_team_key):
            return event.get("faab_bid", 0) or 0
    return 0


if __name__ == "__main__":
    main()
