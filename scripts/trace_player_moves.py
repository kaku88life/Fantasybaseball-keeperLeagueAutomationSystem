"""
Trace how each of the 187 'draft players on wrong team' actually moved.
Distinguish between:
  - trade: inherit original contract (draft price + contract type)
  - drop -> pickup: new A contract with FAAB price (min $1)
"""
import json
from collections import defaultdict
from pathlib import Path


def main():
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    with open("data/contract_verification.json", encoding="utf-8") as f:
        verify_data = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        yahoo_rosters = json.load(f)

    player_history = tx_data["player_history"]
    draft_wrong_team = verify_data["draft_wrong_team"]

    # Build player_key lookup from yahoo rosters
    name_to_key = {}
    for tk, td in yahoo_rosters.items():
        for p in td["players"]:
            name_to_key[(td["manager"], p["name"])] = p.get("player_key", "")

    # Draft lookup by player_key
    draft_by_key = {d["player_key"]: d for d in draft_data}

    # Team key -> manager
    team_key_to_mgr = {
        "458.l.40288.t.1": "Ｋａｋｕ",
        "458.l.40288.t.2": "叫我寬哥",
        "458.l.40288.t.3": "EDDIE",
        "458.l.40288.t.4": "wei",
        "458.l.40288.t.5": "Tony",
        "458.l.40288.t.6": "rawstuff",
        "458.l.40288.t.7": "Billy",
        "458.l.40288.t.8": "YWC",
        "458.l.40288.t.9": "哈寶好",
        "458.l.40288.t.10": "小喆",
        "458.l.40288.t.11": "Hyper",
        "458.l.40288.t.12": "TIMMY LIU",
        "458.l.40288.t.13": "謙謙",
        "458.l.40288.t.14": "魚魚",
        "458.l.40288.t.15": "Ponpon",
        "458.l.40288.t.16": "Leo",
    }

    trades = []
    drop_pickups = []
    commish_moves = []
    unknown = []

    for item in draft_wrong_team:
        player_name = item["player"]
        current_mgr = item["current_team"]
        drafted_by = item["drafted_by"]
        draft_cost = item["draft_cost"]

        player_key = name_to_key.get((current_mgr, player_name), "")
        if not player_key or player_key not in player_history:
            unknown.append(item)
            continue

        history = player_history[player_key]

        # Sort history by timestamp
        history_sorted = sorted(history, key=lambda e: e["timestamp"])

        # Find how this player got to current team
        # Look for the most recent "add" or "trade" to current team
        current_team_adds = [
            e for e in history_sorted
            if e["transaction_type"] in ("add", "trade")
            and team_key_to_mgr.get(e["destination_team_key"], "") == current_mgr
        ]

        if not current_team_adds:
            unknown.append(item)
            continue

        latest_add = current_team_adds[-1]
        tx_type = latest_add["type"]  # trade, add/drop, add, commish

        if tx_type == "trade":
            # Find the original contract
            # The player inherited the contract from the trading team
            # Need to trace back: what contract did the previous team have?
            source_mgr = team_key_to_mgr.get(latest_add["source_team_key"], "?")
            trades.append({
                **item,
                "acquisition": "trade",
                "from_team": source_mgr,
                "note": f"Traded from {source_mgr}, inherits contract",
            })
        elif tx_type in ("add/drop", "add"):
            faab = latest_add.get("faab_bid")
            src_type = latest_add.get("source_type", "")
            faab_cost = max(faab, 1) if faab is not None else 1
            drop_pickups.append({
                **item,
                "acquisition": "faab_pickup",
                "faab_bid": faab,
                "faab_salary": faab_cost,
                "source_type": src_type,
                "note": f"Picked up from {src_type} for FAAB ${faab} -> salary ${faab_cost}",
            })
        elif tx_type == "commish":
            commish_moves.append({
                **item,
                "acquisition": "commish",
                "note": "Commissioner move",
            })
        else:
            unknown.append({**item, "tx_type": tx_type})

    # Print results
    print("=" * 70)
    print(f"TRADES ({len(trades)} players) - inherit original contract")
    print("=" * 70)
    for p in trades:
        print(f"  {p['player']:30s} | {p['drafted_by']:10s} -> {p['from_team']:10s} "
              f"-> {p['current_team']:10s} | draft ${p['draft_cost']}")

    print()
    print("=" * 70)
    print(f"DROP -> PICKUP ({len(drop_pickups)} players) - new A contract")
    print("=" * 70)
    for p in sorted(drop_pickups, key=lambda x: x["current_team"]):
        print(f"  {p['player']:30s} | Now: {p['current_team']:10s} | "
              f"FAAB ${str(p['faab_bid']):>3s} -> salary ${p['faab_salary']}")

    if commish_moves:
        print()
        print("=" * 70)
        print(f"COMMISSIONER MOVES ({len(commish_moves)} players)")
        print("=" * 70)
        for p in commish_moves:
            print(f"  {p['player']:30s} | {p['current_team']}")

    if unknown:
        print()
        print("=" * 70)
        print(f"UNKNOWN ({len(unknown)} players)")
        print("=" * 70)
        for p in unknown:
            print(f"  {p['player']:30s} | {p['current_team']}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Trades (inherit contract):    {len(trades)}")
    print(f"  Drop->Pickup (new A):         {len(drop_pickups)}")
    print(f"  Commissioner moves:           {len(commish_moves)}")
    print(f"  Unknown:                      {len(unknown)}")

    # Save
    result = {
        "trades": trades,
        "drop_pickups": drop_pickups,
        "commish_moves": commish_moves,
        "unknown": unknown,
    }
    with open("data/player_moves_resolved.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved to data/player_moves_resolved.json")


if __name__ == "__main__":
    main()
