"""Debug Sandy Alcantara and other problematic players."""
import json
from datetime import datetime


def main():
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx_data = json.load(f)
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        rosters = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft_data = json.load(f)

    player_history = tx_data["player_history"]
    tk_to_mgr = {tk: td["manager"] for tk, td in rosters.items()}
    draft_by_key = {d["player_key"]: d for d in draft_data}

    # Find players by name
    name_to_pk = {}
    for tk, td in rosters.items():
        for p in td["players"]:
            name_to_pk[p["name"]] = p.get("player_key", "")

    targets = ["Sandy Alcantara", "Nathaniel Lowe", "Lucas Giolito",
               "David Peterson"]

    for name in targets:
        pk = name_to_pk.get(name, "")
        if not pk:
            # Search partial
            for n, k in name_to_pk.items():
                if name.lower() in n.lower():
                    pk = k
                    name = n
                    break
        if not pk:
            print(f"\n{name}: NOT FOUND")
            continue

        print(f"\n{'='*70}")
        print(f"{name} (pk={pk})")

        di = draft_by_key.get(pk)
        if di:
            print(f"  Draft: ${di['cost']} by {tk_to_mgr.get(di['team_key'], '?')}")
        else:
            print("  Not drafted 2025")

        if pk in player_history:
            history = sorted(player_history[pk], key=lambda e: e["timestamp"])
            print(f"  History ({len(history)} events):")
            for e in history:
                ts = int(e["timestamp"]) if e["timestamp"] else 0
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
                src = tk_to_mgr.get(e.get("source_team_key", ""), e.get("source_type", "?"))
                dst = tk_to_mgr.get(e.get("destination_team_key", ""), e.get("destination_type", "?"))
                faab = e.get("faab_bid")
                print(f"    {dt} | {e['type']:10s} | {e['transaction_type']:5s} | "
                      f"{src:12s} -> {dst:12s} | FAAB={faab}")
        else:
            print("  No history")


if __name__ == "__main__":
    main()
