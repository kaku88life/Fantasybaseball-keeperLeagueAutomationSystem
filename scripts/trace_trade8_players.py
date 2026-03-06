"""
Trace Trade #8 players and check for missing transactions.
Also verify all traded players' current locations.
"""
import json
from datetime import datetime

with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
    rosters = json.load(f)
with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
    draft = json.load(f)
with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
    tx_data = json.load(f)

player_history = tx_data["player_history"]
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

# Build current roster lookup
current_roster = {}
for tk, td in rosters.items():
    for p in td["players"]:
        pk = p.get("player_key", "")
        if pk:
            current_roster[pk] = td["manager"]

# All traded players from all 9 trades
trades = sorted(
    [t for t in tx_data["transactions"] if t["type"] == "trade"],
    key=lambda t: int(t["timestamp"]) if t["timestamp"] else 0
)

print("=" * 90)
print("ALL TRADED PLAYERS - CURRENT LOCATION vs TRADE DESTINATION")
print("=" * 90)

mismatches = []
for i, trade in enumerate(trades, 1):
    ts = int(trade["timestamp"]) if trade["timestamp"] else 0
    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
    print(f"\nTrade #{i} ({dt}):")

    for p in trade["players"]:
        name = p["name"]
        pk = p["player_key"]
        trade_dest = team_key_to_mgr.get(p["destination_team_key"], "?")
        trade_src = team_key_to_mgr.get(p["source_team_key"], "?")
        current = current_roster.get(pk, "NOT ON ROSTER")

        # Get contract source
        di = draft_by_key.get(pk)
        draft_cost = f"draft ${di['cost']}" if di else "not drafted"

        # Check FAAB history
        faab_info = ""
        if pk in player_history:
            for e in player_history[pk]:
                if e["transaction_type"] == "add" and e.get("faab_bid") is not None:
                    faab_info = f"FAAB ${e['faab_bid']}"
                    break

        status = "OK" if current == trade_dest else "MOVED"
        if status == "MOVED":
            mismatches.append({
                "name": name, "pk": pk,
                "trade_dest": trade_dest, "current": current,
            })

        contract_src = faab_info if faab_info else draft_cost
        print(f"  {name:30s} | {trade_src:10s} -> {trade_dest:10s} | "
              f"Now: {current:10s} | {status:5s} | {contract_src}")

print(f"\n{'=' * 90}")
print(f"MISMATCHES: {len(mismatches)} players not on trade destination team")
print("=" * 90)

for m in mismatches:
    pk = m["pk"]
    print(f"\n  {m['name']:30s} | Expected: {m['trade_dest']:10s} | Actual: {m['current']}")

    # Check ALL transaction history
    if pk in player_history:
        history = sorted(player_history[pk], key=lambda e: e["timestamp"])
        print(f"  Full history:")
        for e in history:
            ts = int(e["timestamp"]) if e["timestamp"] else 0
            dt = datetime.fromtimestamp(ts).strftime("%m/%d") if ts else "?"
            src = team_key_to_mgr.get(e.get("source_team_key", ""), e.get("source_type", "?"))
            dst = team_key_to_mgr.get(e.get("destination_team_key", ""), e.get("destination_type", "?"))
            print(f"    {dt} | {e['type']:10s} | {e['transaction_type']:5s} | "
                  f"{src:12s} -> {dst:12s} | FAAB={e.get('faab_bid')}")
    else:
        print(f"  No transaction history")
