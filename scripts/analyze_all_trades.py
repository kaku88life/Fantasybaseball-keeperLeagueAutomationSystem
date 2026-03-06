"""
Analyze all traded players:
1. Find their ORIGINAL contract (Excel keeper or draft/FAAB)
2. Track full movement chain
3. Determine current team and correct 2025/2026 contract
"""
import json
import re
import unicodedata
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

YAHOO_MGR_TO_EXCEL = {
    "Ｋａｋｕ": "郭子睿(Rangers)", "叫我寬哥": "Hank",
    "EDDIE": "Eddie Chen", "wei": "Chih-Wei",
    "Tony": "Tony林芳民", "rawstuff": "Issac",
    "Billy": "Billy WU", "YWC": "ywchiou",
    "哈寶好": "楊善合", "小喆": "Yu-Che Chang",
    "Hyper": "林剛", "TIMMY LIU": "TIMMY LIU",
    "謙謙": "Javier", "魚魚": "James Chen",
    "Ponpon": "Ponpon", "Leo": "Leo",
}

TEAM_ABBR = {
    "Ｋａｋｕ": "TEX", "魚魚": "NYY", "叫我寬哥": "PHI",
    "EDDIE": "TOR", "Ponpon": "SEA", "YWC": "DET",
    "Billy": "CHC", "TIMMY LIU": "ARZ",
    "wei": "wei", "Tony": "Tony", "rawstuff": "rawstuff",
    "哈寶好": "哈寶好", "小喆": "小喆", "Hyper": "Hyper",
    "謙謙": "謙謙", "Leo": "Leo",
}


def main():
    # Load data
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        rosters = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)

    player_history = tx_data["player_history"]
    draft_by_key = {d["player_key"]: d for d in draft_data}

    # Load matched data to find keeper contracts
    with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
        matched_data = json.load(f)

    # Build Excel lookup from matched data (keeper players have contract_str)
    excel_by_name = {}
    for yahoo_mgr, team_data in matched_data.items():
        excel_mgr = YAHOO_MGR_TO_EXCEL.get(yahoo_mgr, yahoo_mgr)
        for p in team_data.get("matched", []):
            norm = normalize_name(p["name"])
            excel_by_name[norm] = {
                "name": p["name"],
                "manager": excel_mgr,
                "yahoo_mgr": yahoo_mgr,
                "contract_str": p.get("contract_str", ""),
            }
        # Also check dropped keepers
        for p in team_data.get("dropped", []):
            norm = normalize_name(p["name"])
            excel_by_name[norm] = {
                "name": p["name"],
                "manager": excel_mgr,
                "yahoo_mgr": yahoo_mgr,
                "contract_str": p.get("contract_str", ""),
            }

    # Build current roster lookup
    current_roster = {}
    for tk, td in rosters.items():
        for p in td["players"]:
            pk = p.get("player_key", "")
            if pk:
                current_roster[pk] = td["manager"]

    # Get all trades sorted by date
    trades = sorted(
        [t for t in tx_data["transactions"] if t["type"] == "trade"],
        key=lambda t: int(t["timestamp"]) if t["timestamp"] else 0,
    )

    # User-provided trade contracts (for verification)
    user_contracts = {
        "Zach Neto": "$3/B",
        "Carlos Estévez": "$9/A",
        "Tyler Fitzgerald": "$4/A",
        "David Peterson": "$1/A",
        "Matt Shaw": "$1/R",
        "Nathaniel Lowe": "$7/A",
        "Ryan Pepiot": "$15/A",
        "Matt Strahm": "$1/A",
        "Sandy Alcantara": "$33/N4",
        "Ryan Helsley": "$11/N1",
        "Lucas Giolito": "$1/A",
        "Jhoan Duran": "$11/N1",
        "Mitch Keller": "$1/A",
        "Isaac Collins": "$1/A",
        "Jorge Polanco": "$1/A",
        "Mookie Betts": "$58/O",
        "Corey Seager": "$39/O",
        "Nathan Eovaldi": "$11/O",
        "Devin Williams": "$5/B",
        "Jo Adell": "$1/A",
        "Tyler Locklear": "$1/R",
        "Jared Jones": "$3/B",
        "Matthew Boyd": "$2/A",
        "Jeff Hoffman": "$17/A",
        "Bryan Reynolds": "$16/N1",
        "Ramón Laureano": "$1/A",
        "Royce Lewis": "$11/N2",
        "Ryan Bergert": "$1/A",
    }

    print("=" * 100)
    print("ALL TRADED PLAYERS - COMPLETE CONTRACT ANALYSIS")
    print("=" * 100)

    all_traded = []

    for i, trade in enumerate(trades, 1):
        ts = int(trade["timestamp"]) if trade["timestamp"] else 0
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"

        # Determine teams
        team_set = set()
        for p in trade["players"]:
            src = TEAM_KEY_TO_MGR.get(p["source_team_key"], "?")
            dst = TEAM_KEY_TO_MGR.get(p["destination_team_key"], "?")
            team_set.add(src)
            team_set.add(dst)

        teams_str = " <-> ".join(
            f"{TEAM_ABBR.get(t, t)}({t})" for t in sorted(team_set)
        )
        print(f"\nTrade #{i} ({dt}) | {teams_str}")
        print("-" * 90)

        for p in trade["players"]:
            name = p["name"]
            pk = p["player_key"]
            trade_src = TEAM_KEY_TO_MGR.get(p["source_team_key"], "?")
            trade_dst = TEAM_KEY_TO_MGR.get(p["destination_team_key"], "?")
            current = current_roster.get(pk, "NOT ON ROSTER")

            # Determine original contract
            norm = normalize_name(name)
            excel_info = excel_by_name.get(norm)
            draft_info = draft_by_key.get(pk)

            if excel_info:
                # Was a keeper - use Excel contract
                contract_source = "keeper"
                contract_str = excel_info["contract_str"]
                original_team = excel_info["manager"]
            elif draft_info:
                # Drafted in 2025
                contract_source = "draft"
                contract_str = f"${draft_info['cost']}/A"
                original_team = "draft"
            else:
                # FAAB pickup
                faab_cost = 1
                if pk in player_history:
                    for e in player_history[pk]:
                        if (e["transaction_type"] == "add"
                                and e.get("faab_bid") is not None):
                            faab_cost = max(e["faab_bid"], 1)
                            break
                contract_source = "faab"
                contract_str = f"${faab_cost}/A"
                original_team = "faab"

            user_ct = user_contracts.get(name, "")
            match_mark = ""
            if user_ct:
                if user_ct == contract_str:
                    match_mark = " [OK]"
                else:
                    match_mark = f" [USER: {user_ct}]"

            # Determine how player reached current team
            final_note = ""
            if current == trade_dst:
                final_note = "stayed"
            elif current == "NOT ON ROSTER":
                final_note = "dropped"
            else:
                # Check if dropped then picked up
                if pk in player_history:
                    history = sorted(
                        player_history[pk],
                        key=lambda e: e["timestamp"],
                    )
                    # Find events AFTER this trade
                    post_trade = [
                        e for e in history
                        if int(e["timestamp"]) > ts
                    ]
                    if post_trade:
                        last = post_trade[-1]
                        if last["transaction_type"] == "add":
                            faab = last.get("faab_bid")
                            final_note = f"dropped->pickup FAAB ${faab}"
                        elif last["type"] == "trade":
                            final_note = "traded again"
                        else:
                            final_note = f"post: {last['type']}/{last['transaction_type']}"
                    else:
                        final_note = "no post-trade history"
                else:
                    final_note = "no history"

            src_abbr = TEAM_ABBR.get(trade_src, trade_src)
            dst_abbr = TEAM_ABBR.get(trade_dst, trade_dst)
            cur_abbr = TEAM_ABBR.get(current, current)

            print(
                f"  {name:28s} | {contract_str:10s} ({contract_source:6s}){match_mark:20s}"
                f" | {src_abbr:6s}->{dst_abbr:6s} | Now: {cur_abbr:10s} | {final_note}"
            )

            all_traded.append({
                "trade_num": i,
                "trade_date": dt,
                "player": name,
                "player_key": pk,
                "contract_source": contract_source,
                "contract_at_trade": contract_str,
                "user_contract": user_ct,
                "trade_from": trade_src,
                "trade_to": trade_dst,
                "current_team": current,
                "final_note": final_note,
            })

    # Save
    with open("data/trade_analysis.json", "w", encoding="utf-8") as f:
        json.dump(all_traded, f, indent=2, ensure_ascii=False)
    print(f"\n\nSaved to data/trade_analysis.json")


if __name__ == "__main__":
    main()
