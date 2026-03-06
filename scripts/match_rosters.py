"""
Match Yahoo 2025 end-of-season rosters with Excel contract data and draft results.

This script produces a combined view for each team:
- Players on Yahoo roster matched with their 2025 contract (from Excel)
- Players drafted in 2025 (new A contracts from draft)
- Players on Yahoo roster with no contract info (FAAB/trade acquisitions)
- Players in Excel but not on Yahoo roster (dropped/traded away)
"""
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import openpyxl

from scripts.import_excel import import_yearly_sheet


def normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    # Fullwidth to halfwidth
    name = unicodedata.normalize("NFKC", name)
    # Remove accents
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Lowercase, strip whitespace
    name = name.lower().strip()
    # Remove suffixes like Jr., Sr., II, III, IV
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    # Remove periods
    name = name.replace(".", "")
    # Remove hyphens for matching
    name = name.replace("-", " ")
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)
    return name


def build_excel_lookup(teams_2025):
    """Build a lookup: normalized_name -> (manager, player_data)."""
    lookup = {}
    for team in teams_2025:
        manager = team.manager_name
        for player in team.players:
            key = normalize_name(player.name)
            lookup[key] = {
                "manager": manager,
                "name": player.name,
                "position": player.position,
                "contract_type": player.contract.contract_type.value,
                "salary": player.contract.salary,
                "extension_years": player.contract.extension_years,
                "contract_str": f"${player.contract.salary}/{player.contract.contract_type.value}"
                + (str(player.contract.extension_years) if player.contract.extension_years else ""),
            }
    return lookup


def build_draft_lookup(draft_data):
    """Build a lookup: normalized_name -> draft pick info."""
    lookup = {}
    for pick in draft_data:
        key = normalize_name(pick["player_name"])
        lookup[key] = {
            "name": pick["player_name"],
            "cost": pick["cost"],
            "team_key": pick["team_key"],
            "manager": pick["manager"],
            "round": pick["round"],
            "pick": pick["pick"],
        }
    return lookup


def build_yahoo_manager_map(yahoo_data):
    """Map Yahoo manager nickname -> Excel manager name."""
    # Build manually based on known mappings
    # Yahoo nickname -> Excel manager name
    return {
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


def match_team(yahoo_team, excel_players_for_team, draft_lookup, excel_lookup):
    """Match a single team's Yahoo roster with contract data."""
    results = {
        "matched": [],       # On Yahoo + has contract from Excel
        "draft_new": [],     # On Yahoo + was drafted in 2025 (A contract)
        "no_contract": [],   # On Yahoo + no contract info (FAAB/trade mid-season)
        "dropped": [],       # In Excel but not on Yahoo (dropped/traded)
    }

    yahoo_names = {}
    for p in yahoo_team["players"]:
        key = normalize_name(p["name"])
        yahoo_names[key] = p

    excel_names_matched = set()

    # Match Yahoo players
    for norm_name, yp in yahoo_names.items():
        if norm_name in excel_players_for_team:
            # Matched with contract
            ep = excel_players_for_team[norm_name]
            excel_names_matched.add(norm_name)
            results["matched"].append({
                "name": yp["name"],
                "yahoo_position": yp["position"],
                "yahoo_selected": yp["selected_position"],
                "yahoo_team": yp["team"],
                "yahoo_status": yp.get("status", ""),
                "contract_type": ep["contract_type"],
                "salary": ep["salary"],
                "extension_years": ep["extension_years"],
                "contract_str": ep["contract_str"],
                "source": "keeper",
            })
        elif norm_name in draft_lookup:
            # Drafted in 2025
            dp = draft_lookup[norm_name]
            results["draft_new"].append({
                "name": yp["name"],
                "yahoo_position": yp["position"],
                "yahoo_selected": yp["selected_position"],
                "yahoo_team": yp["team"],
                "yahoo_status": yp.get("status", ""),
                "contract_type": "A",
                "salary": dp["cost"],
                "extension_years": 0,
                "contract_str": f"${dp['cost']}/A",
                "draft_round": dp["round"],
                "draft_pick": dp["pick"],
                "source": "draft",
            })
        else:
            # No contract info - likely FAAB pickup or trade acquisition
            results["no_contract"].append({
                "name": yp["name"],
                "yahoo_position": yp["position"],
                "yahoo_selected": yp["selected_position"],
                "yahoo_team": yp["team"],
                "yahoo_status": yp.get("status", ""),
                "source": "unknown",
            })

    # Find dropped players (in Excel but not on Yahoo)
    for norm_name, ep in excel_players_for_team.items():
        if norm_name not in excel_names_matched:
            results["dropped"].append({
                "name": ep["name"],
                "contract_type": ep["contract_type"],
                "salary": ep["salary"],
                "contract_str": ep["contract_str"],
            })

    return results


def main():
    # Load Yahoo data
    yahoo_file = Path("data/yahoo_2025_rosters.json")
    with open(yahoo_file, encoding="utf-8") as f:
        yahoo_data = json.load(f)

    # Load draft data
    draft_file = Path("data/yahoo_2025_draft.json")
    with open(draft_file, encoding="utf-8") as f:
        draft_data = json.load(f)

    # Load Excel data
    excel_path = r"C:\Users\amy41\OneDrive\Desktop\Baseball\5-Man Keep盟 新版球員名單.xlsx"
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["2025年選秀前名單"]
    teams_2025 = import_yearly_sheet(ws, 2025)

    # Build lookups
    excel_lookup = build_excel_lookup(teams_2025)
    draft_lookup = build_draft_lookup(draft_data)
    manager_map = build_yahoo_manager_map(yahoo_data)

    # Build Excel players indexed by team
    excel_by_team = defaultdict(dict)
    for team in teams_2025:
        for player in team.players:
            key = normalize_name(player.name)
            excel_by_team[team.manager_name][key] = {
                "name": player.name,
                "contract_type": player.contract.contract_type.value,
                "salary": player.contract.salary,
                "extension_years": player.contract.extension_years,
                "contract_str": f"${player.contract.salary}/{player.contract.contract_type.value}"
                + (str(player.contract.extension_years) if player.contract.extension_years else ""),
            }

    # Process each team
    all_results = {}
    total_matched = 0
    total_draft = 0
    total_no_contract = 0
    total_dropped = 0

    for team_key, yahoo_team in yahoo_data.items():
        yahoo_mgr = yahoo_team["manager"]
        excel_mgr = manager_map.get(yahoo_mgr, yahoo_mgr)
        excel_players = excel_by_team.get(excel_mgr, {})

        result = match_team(yahoo_team, excel_players, draft_lookup, excel_lookup)
        all_results[yahoo_mgr] = {
            "yahoo_manager": yahoo_mgr,
            "excel_manager": excel_mgr,
            "team_name": yahoo_team["team_name"],
            **result,
        }

        matched = len(result["matched"])
        draft_new = len(result["draft_new"])
        no_contract = len(result["no_contract"])
        dropped = len(result["dropped"])
        total_matched += matched
        total_draft += draft_new
        total_no_contract += no_contract
        total_dropped += dropped

        print(f"\n{'='*60}")
        print(f"{yahoo_mgr} ({excel_mgr}) - {yahoo_team['team_name']}")
        print(f"{'='*60}")
        print(f"  Keeper matched: {matched}, Draft new: {draft_new}, "
              f"No contract: {no_contract}, Dropped: {dropped}")

        if result["matched"]:
            print(f"\n  --- Keeper (matched) ---")
            for p in sorted(result["matched"], key=lambda x: -x["salary"]):
                status = f" [{p['yahoo_status']}]" if p["yahoo_status"] else ""
                print(f"  {p['contract_str']:>10s}  {p['name']:30s}{status}")

        if result["draft_new"]:
            print(f"\n  --- Draft 2025 (A contract) ---")
            for p in sorted(result["draft_new"], key=lambda x: -x["salary"]):
                status = f" [{p['yahoo_status']}]" if p["yahoo_status"] else ""
                print(f"  {p['contract_str']:>10s}  {p['name']:30s}{status}")

        if result["no_contract"]:
            print(f"\n  --- No contract (FAAB/trade) ---")
            for p in result["no_contract"]:
                status = f" [{p['yahoo_status']}]" if p["yahoo_status"] else ""
                print(f"  {'???':>10s}  {p['name']:30s}{status}")

        if result["dropped"]:
            print(f"\n  --- Dropped/traded (was in Excel) ---")
            for p in result["dropped"]:
                print(f"  {p['contract_str']:>10s}  {p['name']:30s} (no longer on roster)")

    print(f"\n{'='*60}")
    print(f"TOTAL: matched={total_matched}, draft={total_draft}, "
          f"no_contract={total_no_contract}, dropped={total_dropped}")

    # Save results
    output_file = Path("data/matched_2025_rosters.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
