"""
Rebuild the entire contract analysis with the correct 2025 season
team_key -> manager mapping.

Problem: Yahoo reassigned managers to different team_keys between
2025 season and now. The roster data has CURRENT manager assignments,
but the transactions/draft data used SEASON-TIME team_keys.

Solution: Use Excel keeper data to figure out which team_key each
manager had during the 2025 season, then redo everything.
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    name = name.replace(".", "").replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name


# Excel manager -> Yahoo manager name
EXCEL_TO_YAHOO = {
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
YAHOO_TO_EXCEL = {v: k for k, v in EXCEL_TO_YAHOO.items()}


def main():
    # Load data
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        rosters = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
        matched_data = json.load(f)

    player_history = tx_data["player_history"]
    draft_by_key = {d["player_key"]: d for d in draft_data}

    # =====================================================
    # STEP 1: Build correct 2025 SEASON team_key -> manager
    # =====================================================
    # Use Excel keeper names to find which team_key they're on
    # in the Yahoo roster. That tells us the season-time mapping.

    # First, get all keeper names per Excel manager from matched data
    # matched_data uses CURRENT (wrong) manager mapping, but the
    # "matched" players have contract info from Excel. We need to
    # find keepers by name across all rosters.

    # Build: player_name -> team_key from Yahoo rosters
    name_to_team_key = {}
    name_to_player_key = {}
    for tk, td in rosters.items():
        for p in td["players"]:
            name_to_team_key[p["name"]] = tk
            name_to_player_key[p["name"]] = p.get("player_key", "")

    # Build: Excel manager -> list of keeper player names (from matched data)
    # The matched_data keys are CURRENT yahoo managers (wrong mapping),
    # but the "matched" entries have excel contract data.
    # We need to use ALL matched entries across all teams to rebuild.

    # Actually, let's use a different approach: for each team_key in the roster,
    # count how many of each Excel manager's keepers are on that team_key.
    # The team_key with the most matches = that Excel manager's season team.

    # Get all keeper player names per Excel manager from matched_data
    excel_mgr_keepers = defaultdict(list)
    for yahoo_mgr, team_data in matched_data.items():
        excel_mgr = YAHOO_TO_EXCEL.get(yahoo_mgr, yahoo_mgr)
        for p in team_data.get("matched", []):
            excel_mgr_keepers[excel_mgr].append(p["name"])

    # For each Excel manager, find which team_key has their keepers
    print("=" * 70)
    print("STEP 1: Determine correct 2025 season team_key -> manager")
    print("=" * 70)

    season_mapping = {}  # team_key -> yahoo_mgr (season-time)
    current_mapping = {}  # team_key -> yahoo_mgr (current)

    for tk, td in rosters.items():
        current_mapping[tk] = td["manager"]

    for excel_mgr, keeper_names in excel_mgr_keepers.items():
        yahoo_mgr = EXCEL_TO_YAHOO.get(excel_mgr, excel_mgr)
        # Count how many keepers are on each team_key
        tk_counts = Counter()
        for name in keeper_names:
            tk = name_to_team_key.get(name)
            if tk:
                tk_counts[tk] += 1

        if tk_counts:
            best_tk = tk_counts.most_common(1)[0]
            season_mapping[best_tk[0]] = yahoo_mgr
            current_mgr = current_mapping.get(best_tk[0], "?")
            changed = "CHANGED" if current_mgr != yahoo_mgr else "same"
            print(f"  {best_tk[0]:25s} | Season: {yahoo_mgr:12s} | "
                  f"Now: {current_mgr:12s} | {changed} | "
                  f"({best_tk[1]}/{len(keeper_names)} keepers matched)")

    # Fill in any missing team_keys (managers with no keepers matched)
    all_team_keys = set(rosters.keys())
    mapped_tks = set(season_mapping.keys())
    unmapped_tks = all_team_keys - mapped_tks
    mapped_mgrs = set(season_mapping.values())
    all_mgrs = set(EXCEL_TO_YAHOO.values())
    unmapped_mgrs = all_mgrs - mapped_mgrs

    if unmapped_tks:
        print(f"\n  Unmapped team_keys: {unmapped_tks}")
        print(f"  Unmapped managers: {unmapped_mgrs}")
        # For unmapped, we need to check if there's only one option
        if len(unmapped_tks) == 1 and len(unmapped_mgrs) == 1:
            tk = unmapped_tks.pop()
            mgr = unmapped_mgrs.pop()
            season_mapping[tk] = mgr
            print(f"  -> Auto-assigned: {tk} = {mgr}")

    # Save the mapping
    print()
    print("=" * 70)
    print("FINAL SEASON MAPPING")
    print("=" * 70)
    for tk in sorted(season_mapping.keys()):
        s_mgr = season_mapping[tk]
        c_mgr = current_mapping.get(tk, "?")
        print(f"  {tk:25s} | 2025 Season: {s_mgr:12s} | Current: {c_mgr:12s}")

    # =====================================================
    # STEP 2: Re-match rosters with correct mapping
    # =====================================================
    print()
    print("=" * 70)
    print("STEP 2: Re-match Yahoo rosters with correct Excel manager mapping")
    print("=" * 70)

    # Build Excel keeper lookup: (excel_mgr, normalized_name) -> contract info
    # We already have this from matched_data, but keyed by current manager.
    # Let's rebuild from ALL matched + dropped entries.
    excel_contracts = {}
    for yahoo_mgr, team_data in matched_data.items():
        excel_mgr = YAHOO_TO_EXCEL.get(yahoo_mgr, yahoo_mgr)
        for cat in ["matched", "dropped"]:
            for p in team_data.get(cat, []):
                norm = normalize_name(p["name"])
                # Parse extension_years from contract_str if not stored
                ext_years = p.get("extension_years", 0)
                contract_str = p.get("contract_str", "")
                if not ext_years and contract_str:
                    ct, sal, ext = _parse_contract(contract_str)
                    if ct == "N" and ext:
                        ext_years = ext
                excel_contracts[norm] = {
                    "name": p["name"],
                    "excel_mgr": excel_mgr,
                    "yahoo_mgr": yahoo_mgr,
                    "contract_str": contract_str,
                    "contract_type": p.get("contract_type", ""),
                    "salary": p.get("salary", 0),
                    "extension_years": ext_years,
                }

    # For each team_key, use SEASON manager to match with Excel
    new_matched = {}
    for tk, td in rosters.items():
        season_mgr = season_mapping.get(tk, current_mapping.get(tk, "?"))
        excel_mgr = YAHOO_TO_EXCEL.get(season_mgr, season_mgr)

        team_result = {
            "team_key": tk,
            "season_manager": season_mgr,
            "current_manager": current_mapping.get(tk, "?"),
            "excel_manager": excel_mgr,
            "matched": [],     # keeper with contract
            "draft_new": [],   # 2025 draft pick
            "no_contract": [], # FAAB pickup (no prior contract)
            "players": [],     # all players with resolved contracts
        }

        for p in td["players"]:
            player_name = p["name"]
            pk = p.get("player_key", "")
            norm = normalize_name(player_name)
            position = p.get("display_position", "")
            mlb_team = p.get("editorial_team_abbr", "")

            player_entry = {
                "name": player_name,
                "player_key": pk,
                "position": position,
                "mlb_team": mlb_team,
            }

            # Use the unified contract resolver
            resolved = _resolve_effective_contract(
                pk, player_name, draft_by_key, excel_contracts,
                player_history, season_mapping,
            )

            contract_str = resolved.get("contract_str", "A/$1")
            source = resolved.get("source", "unknown")
            was_traded = resolved.get("traded", False)
            excel_mgr_of_contract = resolved.get("excel_mgr", "")

            # Determine category based on source and whether it's on the
            # same team or was traded
            excel_info = excel_contracts.get(norm)

            if source == "keeper" and excel_mgr_of_contract == excel_mgr:
                # Keeper on same team
                player_entry["source"] = "keeper"
                player_entry["contract_2025"] = contract_str
                player_entry["contract_type"] = resolved.get("type", "")
                player_entry["salary"] = resolved.get("salary", 0)
                player_entry["extension_years"] = resolved.get("extension_years", 0)
                team_result["matched"].append(player_entry)
            elif source == "keeper" and was_traded:
                # Keeper from another team, traded here
                player_entry["source"] = "trade_keeper"
                player_entry["contract_2025"] = contract_str
                player_entry["original_team"] = excel_mgr_of_contract
                team_result["matched"].append(player_entry)
            elif source == "keeper":
                # Keeper from another team, dropped and picked up via FAAB
                # The resolver already set contract to FAAB price
                player_entry["source"] = "faab_ex_keeper"
                player_entry["contract_2025"] = contract_str
                player_entry["contract_type"] = "A"
                player_entry["salary"] = resolved.get("salary", 1)
                if excel_info:
                    player_entry["original_contract"] = excel_info["contract_str"]
                    player_entry["original_team"] = excel_info["excel_mgr"]
                team_result["no_contract"].append(player_entry)
            elif source == "draft" and not was_traded:
                # Stayed on drafting team
                player_entry["source"] = "draft"
                player_entry["contract_2025"] = contract_str
                player_entry["contract_type"] = "A"
                player_entry["salary"] = resolved.get("salary", 1)
                team_result["draft_new"].append(player_entry)
            elif source in ("draft", "faab", "faab_same_team") and was_traded:
                # Traded player (originally draft or FAAB) - inherits contract
                player_entry["source"] = f"trade_{source}"
                player_entry["contract_2025"] = contract_str
                player_entry["contract_type"] = resolved.get("type", "A")
                player_entry["salary"] = resolved.get("salary", 1)
                team_result["draft_new"].append(player_entry)
            else:
                # FAAB pickup (not traded), or unknown
                player_entry["source"] = source if source != "unknown" else "faab"
                player_entry["contract_2025"] = contract_str
                player_entry["contract_type"] = "A"
                player_entry["salary"] = resolved.get("salary", 1)
                team_result["no_contract"].append(player_entry)

            team_result["players"].append(player_entry)

        new_matched[season_mgr] = team_result

        keeper_count = len(team_result["matched"])
        draft_count = len(team_result["draft_new"])
        faab_count = len(team_result["no_contract"])
        total = len(team_result["players"])
        current_mgr = current_mapping.get(tk, "?")
        mgr_note = f" (now: {current_mgr})" if current_mgr != season_mgr else ""
        print(f"  {season_mgr:12s}{mgr_note:20s} | "
              f"Total: {total:2d} | Keeper: {keeper_count:2d} | "
              f"Draft: {draft_count:2d} | FAAB: {faab_count:2d}")

    # =====================================================
    # STEP 3: Generate 2026 contracts
    # =====================================================
    print()
    print("=" * 70)
    print("STEP 3: 2026 Contract Evolution")
    print("=" * 70)

    all_teams_2026 = {}
    for season_mgr, team_data in sorted(new_matched.items()):
        current_mgr = team_data["current_manager"]
        excel_mgr = team_data["excel_manager"]

        team_2026 = {
            "team_key": team_data["team_key"],
            "season_2025_manager": season_mgr,
            "current_manager": current_mgr,
            "excel_manager": excel_mgr,
            "players": [],
        }

        for p in team_data["players"]:
            contract_2025 = p.get("contract_2025", "A/$1")
            # Parse contract
            ct, sal, ext = _parse_contract(contract_2025)

            # Evolve to 2026
            new_ct, new_sal, new_ext = _evolve_contract(ct, sal, ext)

            p2026 = {
                **p,
                "contract_2025": contract_2025,
                "contract_2026_type": new_ct,
                "contract_2026_salary": new_sal,
                "contract_2026_ext": new_ext,
                "can_keep": new_ct is not None,
            }
            if new_ct:
                ext_str = str(new_ext) if new_ext else ""
                p2026["contract_2026"] = f"{new_ct}{ext_str}/${new_sal}"
            else:
                p2026["contract_2026"] = "EXPIRED"

            team_2026["players"].append(p2026)

        all_teams_2026[season_mgr] = team_2026

        # Print summary
        players = team_2026["players"]
        can_keep = [p for p in players if p["can_keep"]]
        expired = [p for p in players if not p["can_keep"]]
        mgr_note = f" (now: {current_mgr})" if current_mgr != season_mgr else ""
        print(f"\n  {season_mgr}{mgr_note}")
        print(f"    Total: {len(players)} | Can keep: {len(can_keep)} | "
              f"Expired: {len(expired)}")
        if expired:
            for p in expired:
                print(f"      EXPIRED: {p['name']:30s} | {p['contract_2025']}")

    # Summary
    total_players = sum(len(t["players"]) for t in all_teams_2026.values())
    total_keepable = sum(
        sum(1 for p in t["players"] if p["can_keep"])
        for t in all_teams_2026.values()
    )
    total_expired = total_players - total_keepable
    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_players} players | "
          f"Keepable: {total_keepable} | Expired: {total_expired}")
    print("=" * 70)

    # Save
    save_data = {
        "season_mapping": {tk: mgr for tk, mgr in season_mapping.items()},
        "current_mapping": current_mapping,
        "teams": all_teams_2026,
    }
    with open("data/2026_contracts_v2.json", "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to data/2026_contracts_v2.json")


def _resolve_effective_contract(pk, player_name, draft_by_key, excel_contracts,
                                player_history, season_mapping):
    """Determine effective 2025 contract by tracing the full acquisition chain.

    Rules:
    - Keeper on same team: keeper contract
    - Keeper dropped + FAAB by different team: FAAB price (A contract)
    - Draft + stayed: draft price (A)
    - Draft + dropped by draft team + FAAB by other: FAAB price (A)
    - Any trade: inherits the contract the source team had
    - FAAB pickup: A contract at max(FAAB_bid, $1)
    """
    norm = normalize_name(player_name)
    di = draft_by_key.get(pk)
    excel = excel_contracts.get(norm)

    # Start with initial contract
    if excel:
        contract = {
            "type": excel.get("contract_type", "A"),
            "salary": excel.get("salary", 1),
            "source": "keeper",
            "contract_str": excel.get("contract_str", ""),
            "excel_mgr": excel.get("excel_mgr", ""),
            "extension_years": excel.get("extension_years", 0),
        }
    elif di:
        contract = {
            "type": "A",
            "salary": di["cost"],
            "source": "draft",
            "contract_str": f"A/${di['cost']}",
        }
    else:
        contract = {
            "type": "A",
            "salary": 1,
            "source": "unknown",
            "contract_str": "A/$1",
        }

    # Walk through history chronologically to track contract changes
    if pk in player_history:
        history = sorted(player_history[pk], key=lambda e: e["timestamp"])
        for e in history:
            if e["transaction_type"] == "drop":
                # Player was dropped - contract resets on next pickup
                contract["_dropped"] = True
            elif e["transaction_type"] == "add" and e["type"] != "trade":
                # FAAB pickup
                faab = e.get("faab_bid")
                salary = max(faab, 1) if faab is not None else 1
                dst_tk = e.get("destination_team_key", "")

                if contract.get("_dropped"):
                    # Was dropped first - check if same team re-pickup
                    src_mgr = contract.get("excel_mgr", "")
                    dst_mgr = season_mapping.get(dst_tk, "")
                    dst_excel = YAHOO_TO_EXCEL.get(dst_mgr, dst_mgr)

                    if src_mgr and src_mgr == dst_excel and contract["source"] in ("keeper", "draft"):
                        # Same team re-pickup: preserve original contract type,
                        # use max(original, FAAB) for salary
                        orig_sal = contract["salary"]
                        salary = max(orig_sal, salary)
                        contract["salary"] = salary
                        # Preserve original type (e.g., N4 stays N4, not A)
                        ct = contract.get("type", "A")
                        ext = contract.get("extension_years", 0)
                        if ct == "N" and ext:
                            contract["contract_str"] = f"${salary}/N{ext}"
                        else:
                            contract["contract_str"] = f"${salary}/{ct}" if ct != "A" else f"A/${salary}"
                        contract["source"] = "keeper"  # keep as keeper
                    else:
                        # Different team pickup: new A contract at FAAB
                        contract = {
                            "type": "A",
                            "salary": salary,
                            "source": "faab",
                            "contract_str": f"A/${salary}",
                        }
                else:
                    # First acquisition via FAAB (no prior drop)
                    contract = {
                        "type": "A",
                        "salary": salary,
                        "source": "faab",
                        "contract_str": f"A/${salary}",
                    }

                contract.pop("_dropped", None)

            elif e["type"] == "trade":
                # Trade inherits existing contract (no change to contract)
                contract["traded"] = True
                contract["trade_dest_tk"] = e.get("destination_team_key", "")
                contract.pop("_dropped", None)

    return contract


def _parse_contract(contract_str: str):
    """Parse contract string like '$51/N7', 'A/$5', '$9/A' etc."""
    if not contract_str:
        return "A", 1, 0

    # Handle formats: "$51/N7", "A/$5", "$9/A", "O/$20"
    contract_str = contract_str.strip()

    # Try format: $salary/TypeExt (e.g., $51/N7, $9/A, $20/O)
    m = re.match(r"\$(\d+)/([ABONR])(\d*)", contract_str)
    if m:
        sal = int(m.group(1))
        ct = m.group(2)
        ext = int(m.group(3)) if m.group(3) else 0
        return ct, sal, ext

    # Try format: Type/$salary (e.g., A/$5)
    m = re.match(r"([ABONR])(\d*)/\$(\d+)", contract_str)
    if m:
        ct = m.group(1)
        ext = int(m.group(2)) if m.group(2) else 0
        sal = int(m.group(3))
        return ct, sal, ext

    return "A", 1, 0


def _evolve_contract(contract_type, salary, extension_years):
    """Evolve contract from 2025 to 2026."""
    if contract_type == "A":
        return "B", salary, 0
    elif contract_type == "B":
        return "O", salary, 0
    elif contract_type == "N":
        # N contract salary is FIXED throughout the contract period.
        # The $5/year is only added once at B->N extension time, not annually.
        if extension_years and extension_years > 1:
            return "N", salary, extension_years - 1
        else:
            return "O", salary, 0
    elif contract_type == "O":
        return None, None, None
    elif contract_type == "R":
        return "R", salary, 0
    else:
        return contract_type, salary, 0


if __name__ == "__main__":
    main()
