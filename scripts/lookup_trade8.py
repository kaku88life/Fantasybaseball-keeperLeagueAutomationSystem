"""Look up Trade #8 players' contract origins."""
import json
from datetime import datetime

with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
    rosters = json.load(f)
with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
    draft = json.load(f)
with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
    tx = json.load(f)
with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
    matched = json.load(f)

player_history = tx["player_history"]
draft_by_key = {d["player_key"]: d for d in draft}

team_key_to_mgr = {
    "458.l.40288.t.1": "Kaku", "458.l.40288.t.2": "叫我寬哥",
    "458.l.40288.t.3": "EDDIE", "458.l.40288.t.4": "wei",
    "458.l.40288.t.5": "Tony", "458.l.40288.t.6": "rawstuff",
    "458.l.40288.t.7": "Billy", "458.l.40288.t.8": "YWC",
    "458.l.40288.t.9": "哈寶好", "458.l.40288.t.10": "小喆",
    "458.l.40288.t.11": "Hyper", "458.l.40288.t.12": "TIMMY LIU",
    "458.l.40288.t.13": "謙謙", "458.l.40288.t.14": "魚魚",
    "458.l.40288.t.15": "Ponpon", "458.l.40288.t.16": "Leo",
}

targets = ["David Peterson", "José Berríos", "Vladimir Guerrero Jr."]

for target in targets:
    print(f"=== {target} ===")
    pk = None
    current_team = None
    for tk, td in rosters.items():
        for p in td["players"]:
            if p["name"] == target:
                pk = p.get("player_key", "")
                current_team = td["manager"]
                break
        if pk:
            break

    if not pk:
        print(f"  Not on any current roster")
        for d in draft:
            if target.lower() in d.get("player_name", "").lower():
                slot_owner = team_key_to_mgr.get(d["team_key"], "?")
                print(f"  Draft: {d['player_name']} cost=${d['cost']} slot={slot_owner}")
                pk = d["player_key"]
                break
    else:
        print(f"  Current team: {current_team}, key: {pk}")

    if pk and pk in draft_by_key:
        d = draft_by_key[pk]
        slot_owner = team_key_to_mgr.get(d["team_key"], "?")
        print(f"  Draft: cost=${d['cost']}, round={d['round']}, slot_owner={slot_owner}")

    # Check matched category
    if current_team:
        for cat in ["matched", "draft_new", "no_contract", "dropped"]:
            for p in matched.get(current_team, {}).get(cat, []):
                if p["name"] == target:
                    print(f"  Matched category: {cat}")
                    if "contract_str" in p:
                        print(f"  Excel contract: {p['contract_str']}")
                    break

    if pk and pk in player_history:
        history = sorted(player_history[pk], key=lambda e: e["timestamp"])
        print(f"  Transaction history ({len(history)} events):")
        for e in history:
            ts = int(e["timestamp"]) if e["timestamp"] else 0
            dt = datetime.fromtimestamp(ts).strftime("%m/%d") if ts else "?"
            src = team_key_to_mgr.get(e.get("source_team_key", ""), e.get("source_type", "?"))
            dst = team_key_to_mgr.get(e.get("destination_team_key", ""), e.get("destination_type", "?"))
            faab = e.get("faab_bid")
            print(f"    {dt} | {e['type']:10s} | {e['transaction_type']:5s} | "
                  f"{src:12s} -> {dst:12s} | FAAB={faab}")
    elif pk:
        print(f"  No transaction history")
    print()
