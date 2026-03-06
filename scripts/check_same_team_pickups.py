"""
Check if any FAAB-acquired player was previously on the same team with an
existing contract (dropped then re-acquired). Per league rules:
  - Same team re-pickup: maintain original contract
  - Different team pickup: new A contract with FAAB price
"""
import json
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

import openpyxl
from scripts.import_excel import import_yearly_sheet


def normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    name = unicodedata.normalize("NFKC", name)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    name = name.replace(".", "").replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name


def main():
    # Load transaction history
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    player_history = tx_data["player_history"]

    # Load Excel 2025 keeper data (start of season contracts)
    excel_path = r"C:\Users\amy41\OneDrive\Desktop\Baseball\5-Man Keep盟 新版球員名單.xlsx"
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["2025年選秀前名單"]
    teams_2025 = import_yearly_sheet(ws, 2025)

    # Build Excel lookup: normalized_name -> {manager, contract}
    # Also map manager -> team_keys from Yahoo
    excel_contracts = {}
    for team in teams_2025:
        for player in team.players:
            key = normalize_name(player.name)
            excel_contracts[key] = {
                "name": player.name,
                "manager": team.manager_name,
                "contract_type": player.contract.contract_type.value,
                "salary": player.contract.salary,
                "extension_years": player.contract.extension_years,
                "contract_str": f"${player.contract.salary}/{player.contract.contract_type.value}"
                    + (str(player.contract.extension_years) if player.contract.extension_years else ""),
            }

    # Load matched data to get the "no_contract" players
    with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
        matched_data = json.load(f)

    # Also load draft lookup to get player_keys
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        yahoo_rosters = json.load(f)

    # Excel manager -> Yahoo team_key mapping
    manager_to_yahoo = {
        "郭子睿(Rangers)": "Ｋａｋｕ",
        "Hank": "叫我寬哥",
        "Eddie Chen": "EDDIE",
        "Chih-Wei": "wei",
        "Tony林芳民": "Tony",
        "Issac": "rawstuff",
        "Billy WU": "Billy",
        "ywchiou": "YWC",
        "楊善合": "哈寶好",
        "Yu-Che Chang": "小喆",
        "林剛": "Hyper",
        "TIMMY LIU": "TIMMY LIU",
        "Javier": "謙謙",
        "James Chen": "魚魚",
        "Ponpon": "Ponpon",
        "Leo": "Leo",
    }
    yahoo_to_excel = {v: k for k, v in manager_to_yahoo.items()}

    # For each "no_contract" player, check if they had a prior contract
    # and were dropped then re-acquired by the same team
    same_team_pickups = []
    different_team_pickups = []

    for yahoo_mgr, team_data in matched_data.items():
        excel_mgr = yahoo_to_excel.get(yahoo_mgr, yahoo_mgr)
        no_contract = team_data.get("no_contract", [])

        for p in no_contract:
            player_name = p["name"]
            norm = normalize_name(player_name)

            # Check if this player had a contract at the start of 2025
            if norm not in excel_contracts:
                continue  # No prior contract, just a FAAB pickup with no history

            prior = excel_contracts[norm]
            prior_mgr = prior["manager"]

            # Find the player_key from yahoo roster
            player_key = None
            for tk, td in yahoo_rosters.items():
                if td["manager"] == yahoo_mgr:
                    for yp in td["players"]:
                        if yp["name"] == player_name:
                            player_key = yp.get("player_key", "")
                            break
                    break

            if not player_key or player_key not in player_history:
                continue

            history = player_history[player_key]

            # Was this player originally on the same team?
            if prior_mgr == excel_mgr:
                # Same team dropped and re-acquired
                same_team_pickups.append({
                    "player": player_name,
                    "manager": yahoo_mgr,
                    "excel_manager": excel_mgr,
                    "original_contract": prior["contract_str"],
                    "original_type": prior["contract_type"],
                    "original_salary": prior["salary"],
                    "action": "MAINTAIN_CONTRACT",
                })
            else:
                # Different team picked up a player with prior contract
                # Find FAAB cost
                adds = [e for e in history if e["transaction_type"] == "add"]
                faab = adds[-1]["faab_bid"] if adds else 0
                different_team_pickups.append({
                    "player": player_name,
                    "current_manager": yahoo_mgr,
                    "original_manager": prior_mgr,
                    "original_contract": prior["contract_str"],
                    "faab_cost": faab,
                    "action": "NEW_A_CONTRACT",
                })

    print("=" * 60)
    print("SAME TEAM RE-PICKUPS (maintain original contract)")
    print("=" * 60)
    if same_team_pickups:
        for p in same_team_pickups:
            print(f"  {p['player']:30s} | {p['manager']:10s} | Original: {p['original_contract']}")
    else:
        print("  (none)")

    print()
    print("=" * 60)
    print("DIFFERENT TEAM PICKUPS (new A contract with FAAB price)")
    print("=" * 60)
    if different_team_pickups:
        for p in different_team_pickups:
            print(f"  {p['player']:30s} | Now: {p['current_manager']:10s} | "
                  f"Was: {p['original_manager']:15s} | Original: {p['original_contract']} | "
                  f"FAAB: ${p['faab_cost']}")
    else:
        print("  (none)")

    # Save for later use
    result = {
        "same_team_pickups": same_team_pickups,
        "different_team_pickups": different_team_pickups,
    }
    with open("data/contract_resolution.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to data/contract_resolution.json")


if __name__ == "__main__":
    main()
