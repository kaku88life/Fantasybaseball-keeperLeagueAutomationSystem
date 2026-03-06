"""Debug player history for specific players to check FAAB bids and transactions."""
import json
from datetime import datetime


def main():
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        rosters = json.load(f)

    player_history = tx_data["player_history"]

    # Build team_key -> manager
    tk_to_mgr = {}
    for tk, td in rosters.items():
        tk_to_mgr[tk] = td["manager"]

    # Build name -> player_key lookup
    name_to_pk = {}
    for tk, td in rosters.items():
        for p in td["players"]:
            name_to_pk[p["name"]] = p.get("player_key", "")

    targets = ["Jo Adell", "Tyler Locklear", "Ramón Laureano", "Jhoan Duran",
               "Jared Jones", "Vladimir Guerrero Jr."]

    draft_by_key = {d["player_key"]: d for d in draft_data}

    for name in targets:
        pk = name_to_pk.get(name, "")
        if not pk:
            print(f"\n{'='*60}")
            print(f"{name}: NOT ON ANY ROSTER")
            continue

        print(f"\n{'='*60}")
        print(f"{name} (player_key={pk})")

        # Draft info
        di = draft_by_key.get(pk)
        if di:
            draft_tk = di["team_key"]
            draft_mgr = tk_to_mgr.get(draft_tk, "?")
            print(f"  Draft: Round {di['round']}, Pick {di['pick']}, "
                  f"Cost ${di['cost']}, Team: {draft_mgr} ({draft_tk})")
        else:
            print("  Draft: NOT DRAFTED in 2025")

        # Transaction history
        if pk in player_history:
            history = sorted(player_history[pk], key=lambda e: e["timestamp"])
            print(f"  Transaction history ({len(history)} events):")
            for e in history:
                ts = int(e["timestamp"]) if e["timestamp"] else 0
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
                src_tk = e.get("source_team_key", "")
                dst_tk = e.get("destination_team_key", "")
                src = tk_to_mgr.get(src_tk, e.get("source_type", "?"))
                dst = tk_to_mgr.get(dst_tk, e.get("destination_type", "?"))
                faab = e.get("faab_bid")
                tx_type = e["transaction_type"]
                ev_type = e["type"]
                faab_str = f"FAAB=${faab}" if faab is not None else ""
                print(f"    {dt} | {ev_type:10s} | {tx_type:5s} | "
                      f"{src:12s} -> {dst:12s} | {faab_str}")
        else:
            print("  No transaction history")


if __name__ == "__main__":
    main()
