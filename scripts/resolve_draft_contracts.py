"""
Resolve contracts for all draft_new players (2025 draft picks currently on rosters).

The draft data's team_key refers to the ORIGINAL pick owner, not the team
that actually selected the player (draft picks can be traded). So we use
transaction history to determine how each player reached their current team:

1. No transaction history -> stayed on drafting team -> A at draft cost
2. Traded -> inherit contract -> A at draft cost
3. Dropped & picked up by different team -> new A at max(FAAB, 1)
"""
import json


def main():
    with open("data/matched_2025_rosters.json", encoding="utf-8") as f:
        matched = json.load(f)
    with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
        rosters = json.load(f)
    with open("data/yahoo_2025_draft.json", encoding="utf-8") as f:
        draft = json.load(f)
    with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
        tx = json.load(f)

    player_history = tx["player_history"]
    draft_by_key = {d["player_key"]: d for d in draft}

    team_key_to_mgr = {
        "458.l.40288.t.1": "Ｋａｋｕ", "458.l.40288.t.2": "叫我寬哥",
        "458.l.40288.t.3": "EDDIE", "458.l.40288.t.4": "wei",
        "458.l.40288.t.5": "Tony", "458.l.40288.t.6": "rawstuff",
        "458.l.40288.t.7": "Billy", "458.l.40288.t.8": "YWC",
        "458.l.40288.t.9": "哈寶好", "458.l.40288.t.10": "小喆",
        "458.l.40288.t.11": "Hyper", "458.l.40288.t.12": "TIMMY LIU",
        "458.l.40288.t.13": "謙謙", "458.l.40288.t.14": "魚魚",
        "458.l.40288.t.15": "Ponpon", "458.l.40288.t.16": "Leo",
    }
    mgr_to_team_key = {v: k for k, v in team_key_to_mgr.items()}

    stayed_on_team = []
    traded_to_team = []
    faab_pickup = []

    for yahoo_mgr, team_data in matched.items():
        current_tk = mgr_to_team_key.get(yahoo_mgr, "")
        for p in team_data.get("draft_new", []):
            name = p["name"]
            pk = _find_player_key(rosters, yahoo_mgr, name)
            if not pk:
                continue

            draft_info = draft_by_key.get(pk, {})
            draft_cost = draft_info.get("cost", 0)

            if pk not in player_history:
                stayed_on_team.append({
                    "player": name, "team": yahoo_mgr,
                    "draft_cost": draft_cost,
                    "contract_type": "A", "salary": draft_cost,
                    "reason": "no_transactions",
                })
            else:
                history = player_history[pk]
                adds_to_current = [
                    e for e in history
                    if e["transaction_type"] in ("add", "trade")
                    and e.get("destination_team_key") == current_tk
                ]
                if adds_to_current:
                    latest = adds_to_current[-1]
                    if latest["type"] == "trade":
                        from_team = team_key_to_mgr.get(
                            latest.get("source_team_key", ""), "?"
                        )
                        traded_to_team.append({
                            "player": name, "team": yahoo_mgr,
                            "draft_cost": draft_cost,
                            "from_team": from_team,
                            "contract_type": "A", "salary": draft_cost,
                            "reason": "trade_inherit",
                        })
                    else:
                        faab = latest.get("faab_bid")
                        salary = max(faab, 1) if faab is not None else 1
                        faab_pickup.append({
                            "player": name, "team": yahoo_mgr,
                            "draft_cost": draft_cost,
                            "faab_bid": faab, "salary": salary,
                            "contract_type": "A",
                            "reason": "faab_pickup",
                        })
                else:
                    # Has history but no add/trade to current team
                    # Likely same-team drop+re-add or history unrelated
                    stayed_on_team.append({
                        "player": name, "team": yahoo_mgr,
                        "draft_cost": draft_cost,
                        "contract_type": "A", "salary": draft_cost,
                        "reason": "same_team_history",
                    })

    total = len(stayed_on_team) + len(traded_to_team) + len(faab_pickup)
    print("=" * 70)
    print(f"DRAFT_NEW CONTRACT RESOLUTION ({total} players)")
    print("=" * 70)
    print(f"  Stayed on team (A at draft cost):   {len(stayed_on_team)}")
    print(f"  Traded (inherit A at draft cost):    {len(traded_to_team)}")
    print(f"  FAAB pickup (new A at FAAB price):   {len(faab_pickup)}")
    print()

    if traded_to_team:
        print("TRADED (inherit contract):")
        for p in traded_to_team:
            print(f"  {p['player']:30s} | {p['team']:10s} | "
                  f"from {p['from_team']:10s} | A/${p['salary']}")
        print()

    if faab_pickup:
        print("FAAB PICKUP (new A contract):")
        for p in faab_pickup:
            print(f"  {p['player']:30s} | {p['team']:10s} | "
                  f"draft ${p['draft_cost']} -> FAAB ${p['faab_bid']} "
                  f"-> salary ${p['salary']}")

    result = {
        "stayed_on_team": stayed_on_team,
        "traded": traded_to_team,
        "faab_pickup": faab_pickup,
    }
    with open("data/draft_new_contracts.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to data/draft_new_contracts.json")


def _find_player_key(yahoo_rosters, yahoo_mgr, player_name):
    for tk, td in yahoo_rosters.items():
        if td["manager"] == yahoo_mgr:
            for yp in td["players"]:
                if yp["name"] == player_name:
                    return yp.get("player_key", "")
    return None


if __name__ == "__main__":
    main()
