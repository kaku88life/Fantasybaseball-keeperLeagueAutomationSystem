"""
Generate complete 2026 contract list for all 16 teams.

Combines:
1. Keeper players (matched from Excel) - evolve contract A->B->O, N(x)->N(x-1)->O
2. Draft_new players - A contract at draft cost (or FAAB if picked up by different team)
3. No_contract players - A contract at max(FAAB, 1)

Output: per-team player list with 2025 contract + 2026 contract + keeper options
"""
import json
import re
import unicodedata
from collections import defaultdict

import openpyxl
from scripts.import_excel import import_yearly_sheet


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    name = name.replace(".", "").replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name


# Contract evolution rules
def evolve_contract(contract_type, salary, extension_years):
    """
    Evolve a contract from 2025 to 2026.
    Returns (new_type, new_salary, new_extension_years)

    Rules:
    - A -> B (salary stays)
    - B -> O (salary stays, final year)
    - N(x) where x > 1 -> N(x-1) (salary + $5/yr)
    - N(1) -> O (salary + $5)
    - O -> cannot keep (final year was 2025)
    - R -> stays R (rookie bench contract)
    """
    if contract_type == "A":
        return "B", salary, 0
    elif contract_type == "B":
        return "O", salary, 0
    elif contract_type == "N":
        if extension_years and extension_years > 1:
            return "N", salary + 5, extension_years - 1
        else:
            return "O", salary + 5, 0
    elif contract_type == "O":
        return None, None, None  # Cannot keep
    elif contract_type == "R":
        return "R", salary, 0
    else:
        return contract_type, salary, 0


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

TEAM_KEY_TO_MGR = {
    "458.l.40288.t.1": "Ｋａｋｕ", "458.l.40288.t.2": "叫我寬哥",
    "458.l.40288.t.3": "EDDIE", "458.l.40288.t.4": "wei",
    "458.l.40288.t.5": "Tony", "458.l.40288.t.6": "rawstuff",
    "458.l.40288.t.7": "Billy", "458.l.40288.t.8": "YWC",
    "458.l.40288.t.9": "哈寶好", "458.l.40288.t.10": "小喆",
    "458.l.40288.t.11": "Hyper", "458.l.40288.t.12": "TIMMY LIU",
    "458.l.40288.t.13": "謙謙", "458.l.40288.t.14": "魚魚",
    "458.l.40288.t.15": "Ponpon", "458.l.40288.t.16": "Leo",
}
MGR_TO_TEAM_KEY = {v: k for k, v in TEAM_KEY_TO_MGR.items()}


def main():
    # Load all data
    with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
        matched = json.load(f)
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        yahoo_rosters = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    with open("data/draft_new_contracts.json", encoding="utf-8") as f:
        draft_contracts = json.load(f)

    player_history = tx_data["player_history"]
    draft_by_key = {d["player_key"]: d for d in draft_data}

    # Load Excel 2025 contracts
    excel_path = r"C:\Users\amy41\OneDrive\Desktop\Baseball\5-Man Keep盟 新版球員名單.xlsx"
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["2025年選秀前名單"]
    teams_2025 = import_yearly_sheet(ws, 2025)

    # Build Excel contract lookup by normalized name + manager
    excel_lookup = {}
    for team in teams_2025:
        for player in team.players:
            key = (team.manager_name, normalize_name(player.name))
            excel_lookup[key] = {
                "contract_type": player.contract.contract_type.value,
                "salary": player.contract.salary,
                "extension_years": player.contract.extension_years,
            }

    # Build draft_new lookup for quick access
    draft_new_lookup = {}
    for category in ["stayed_on_team", "traded", "faab_pickup"]:
        for p in draft_contracts.get(category, []):
            draft_new_lookup[(p["team"], p["player"])] = {
                "contract_type": p["contract_type"],
                "salary": p["salary"],
                "source": category,
                "draft_cost": p.get("draft_cost", 0),
            }

    # Build Yahoo roster info lookup
    yahoo_player_info = {}
    for tk, td in yahoo_rosters.items():
        for p in td["players"]:
            yahoo_player_info[(td["manager"], p["name"])] = {
                "player_key": p.get("player_key", ""),
                "position": p.get("display_position", ""),
                "editorial_team": p.get("editorial_team_abbr", ""),
                "status": p.get("status", ""),
            }

    # Generate per-team contract list
    all_teams = {}
    total_players = 0

    for yahoo_mgr in sorted(matched.keys()):
        team_data = matched[yahoo_mgr]
        excel_mgr = YAHOO_MGR_TO_EXCEL.get(yahoo_mgr, yahoo_mgr)
        team_players = []

        # 1. Matched keeper players - evolve contract
        for p in team_data.get("matched", []):
            name = p["name"]
            norm = normalize_name(name)
            excel_key = (excel_mgr, norm)
            contract_2025 = excel_lookup.get(excel_key, {})
            ct = contract_2025.get("contract_type", "A")
            sal = contract_2025.get("salary", 0)
            ext = contract_2025.get("extension_years", 0)

            new_ct, new_sal, new_ext = evolve_contract(ct, sal, ext)
            info = yahoo_player_info.get((yahoo_mgr, name), {})

            player_entry = {
                "name": name,
                "position": info.get("position", ""),
                "mlb_team": info.get("editorial_team", ""),
                "player_key": info.get("player_key", ""),
                "source": "keeper",
                "contract_2025": f"{ct}" + (f"{ext}" if ext else "") + f"/${sal}",
                "contract_2026_type": new_ct,
                "contract_2026_salary": new_sal,
                "contract_2026_ext": new_ext,
                "can_keep": new_ct is not None,
                "keeper_action": "extend" if new_ct else "cannot_keep",
            }
            if new_ct:
                player_entry["contract_2026"] = (
                    f"{new_ct}" + (f"{new_ext}" if new_ext else "") + f"/${new_sal}"
                )
            else:
                player_entry["contract_2026"] = "EXPIRED"

            team_players.append(player_entry)

        # 2. Draft_new players
        for p in team_data.get("draft_new", []):
            name = p["name"]
            dn = draft_new_lookup.get((yahoo_mgr, name))
            info = yahoo_player_info.get((yahoo_mgr, name), {})

            if dn:
                sal_2025 = dn["salary"]
                source = dn["source"]
            else:
                # Fallback: use draft cost
                pk = info.get("player_key", "")
                di = draft_by_key.get(pk, {})
                sal_2025 = di.get("cost", 1)
                source = "draft"

            # 2025 is A contract, 2026 evolves to B
            player_entry = {
                "name": name,
                "position": info.get("position", ""),
                "mlb_team": info.get("editorial_team", ""),
                "player_key": info.get("player_key", ""),
                "source": f"draft_{source}",
                "contract_2025": f"A/${sal_2025}",
                "contract_2026_type": "B",
                "contract_2026_salary": sal_2025,
                "contract_2026_ext": 0,
                "contract_2026": f"B/${sal_2025}",
                "can_keep": True,
                "keeper_action": "keep",
            }
            team_players.append(player_entry)

        # 3. No_contract players (FAAB pickups with no prior contract)
        for p in team_data.get("no_contract", []):
            name = p["name"]
            info = yahoo_player_info.get((yahoo_mgr, name), {})
            pk = info.get("player_key", "")

            # Find FAAB cost from transaction history
            faab_cost = 1  # minimum
            if pk and pk in player_history:
                current_tk = MGR_TO_TEAM_KEY.get(yahoo_mgr, "")
                for event in reversed(player_history[pk]):
                    if (event["transaction_type"] in ("add", "trade")
                            and event.get("destination_team_key") == current_tk):
                        fb = event.get("faab_bid")
                        if fb is not None:
                            faab_cost = max(fb, 1)
                        elif event["type"] == "trade":
                            # Traded player - need to find their original contract
                            faab_cost = 1  # default for now
                        break

            # 2025 is A contract, 2026 evolves to B
            player_entry = {
                "name": name,
                "position": info.get("position", ""),
                "mlb_team": info.get("editorial_team", ""),
                "player_key": info.get("player_key", ""),
                "source": "faab",
                "contract_2025": f"A/${faab_cost}",
                "contract_2026_type": "B",
                "contract_2026_salary": faab_cost,
                "contract_2026_ext": 0,
                "contract_2026": f"B/${faab_cost}",
                "can_keep": True,
                "keeper_action": "keep",
            }
            team_players.append(player_entry)

        all_teams[yahoo_mgr] = {
            "manager_yahoo": yahoo_mgr,
            "manager_excel": excel_mgr,
            "player_count": len(team_players),
            "players": team_players,
        }
        total_players += len(team_players)

    # Print summary
    print("=" * 70)
    print("2026 CONTRACT LIST - ALL TEAMS")
    print("=" * 70)

    for yahoo_mgr in sorted(all_teams.keys()):
        team = all_teams[yahoo_mgr]
        players = team["players"]
        keepers = [p for p in players if p["source"] == "keeper"]
        drafts = [p for p in players if p["source"].startswith("draft_")]
        faabs = [p for p in players if p["source"] == "faab"]
        can_keep = [p for p in players if p["can_keep"]]
        expired = [p for p in players if not p["can_keep"]]

        print(f"\n  {yahoo_mgr} ({team['manager_excel']})")
        print(f"    Total: {len(players)} | "
              f"Keepers: {len(keepers)} | "
              f"Draft: {len(drafts)} | "
              f"FAAB: {len(faabs)} | "
              f"Can keep: {len(can_keep)} | "
              f"Expired: {len(expired)}")

        if expired:
            print(f"    Expired (O contract, cannot keep):")
            for p in expired:
                print(f"      {p['name']:30s} | {p['contract_2025']}")

    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_players} players across {len(all_teams)} teams")
    print("=" * 70)

    # Count keepable vs expired
    all_keepable = sum(
        1 for t in all_teams.values()
        for p in t["players"] if p["can_keep"]
    )
    all_expired = sum(
        1 for t in all_teams.values()
        for p in t["players"] if not p["can_keep"]
    )
    print(f"  Keepable for 2026: {all_keepable}")
    print(f"  Expired (O):       {all_expired}")

    # Save
    with open("data/2026_contracts.json", "w", encoding="utf-8") as f:
        json.dump(all_teams, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved to data/2026_contracts.json")


if __name__ == "__main__":
    main()
