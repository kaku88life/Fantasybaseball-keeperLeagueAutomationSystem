"""
Fetch all 2025 transactions from Yahoo Fantasy API.

Categorizes each transaction as:
  - add/drop (FAAB waiver or free agent pickup)
  - trade
  - commish (commissioner action)

Saves full transaction data for contract resolution.
"""
import json
from pathlib import Path
from src.api.yahoo_client import YahooFantasyClient

LEAGUE_KEY_2025 = "458.l.40288"


def fetch_all_transactions(client: YahooFantasyClient) -> list[dict]:
    """Fetch all transactions with full player details."""
    data = client._get(f"/league/{LEAGUE_KEY_2025}/transactions")
    tx_data = data["fantasy_content"]["league"][1]["transactions"]
    count = tx_data.get("count", 0)

    transactions = []
    for i in range(count):
        tx_raw = tx_data[str(i)]["transaction"]
        # tx_raw is a list: [meta_dict, players_dict]
        meta = tx_raw[0] if isinstance(tx_raw, list) else tx_raw
        players_section = tx_raw[1] if isinstance(tx_raw, list) and len(tx_raw) > 1 else {}

        tx_entry = {
            "transaction_id": meta.get("transaction_id", ""),
            "type": meta.get("type", ""),
            "status": meta.get("status", ""),
            "timestamp": meta.get("timestamp", ""),
            "faab_bid": None,
            "players": [],
        }

        # Extract FAAB bid if present
        if "faab_bid" in meta:
            tx_entry["faab_bid"] = int(meta["faab_bid"])

        # Parse players involved
        if "players" in players_section:
            players_data = players_section["players"]
            p_count = players_data.get("count", 0)
            for j in range(p_count):
                p_raw = players_data[str(j)]["player"]
                player_info = _parse_tx_player(p_raw)
                tx_entry["players"].append(player_info)

        transactions.append(tx_entry)

    return transactions


def _parse_tx_player(player_raw) -> dict:
    """Parse a player entry from a transaction."""
    info_list = player_raw[0] if isinstance(player_raw, list) else []
    tx_data_raw = player_raw[1] if isinstance(player_raw, list) and len(player_raw) > 1 else {}

    player = {
        "name": "",
        "player_key": "",
        "position": "",
        "editorial_team": "",
        "transaction_type": "",  # add, drop, trade
        "source_type": "",       # freeagents, waivers, team
        "destination_type": "",  # team, waivers, freeagents
        "source_team_key": "",
        "destination_team_key": "",
        "source_team_name": "",
        "destination_team_name": "",
    }

    # Parse player info
    for item in info_list:
        if isinstance(item, dict):
            if "name" in item:
                player["name"] = item["name"].get("full", "")
            if "player_key" in item:
                player["player_key"] = item["player_key"]
            if "display_position" in item:
                player["position"] = item["display_position"]
            if "editorial_team_abbr" in item:
                player["editorial_team"] = item["editorial_team_abbr"]

    # Parse transaction data
    if isinstance(tx_data_raw, dict) and "transaction_data" in tx_data_raw:
        td = tx_data_raw["transaction_data"]
        # Could be a single dict or a list of dicts
        if isinstance(td, list):
            for item in td:
                if isinstance(item, dict):
                    _extract_tx_data(item, player)
        elif isinstance(td, dict):
            _extract_tx_data(td, player)

    return player


def _extract_tx_data(td: dict, player: dict):
    """Extract transaction data fields."""
    if "type" in td:
        player["transaction_type"] = td["type"]
    if "source_type" in td:
        player["source_type"] = td["source_type"]
    if "destination_type" in td:
        player["destination_type"] = td["destination_type"]
    if "source_team_key" in td:
        player["source_team_key"] = td["source_team_key"]
    if "destination_team_key" in td:
        player["destination_team_key"] = td["destination_team_key"]
    if "source_team_name" in td:
        player["source_team_name"] = td["source_team_name"]
    if "destination_team_name" in td:
        player["destination_team_name"] = td["destination_team_name"]


def categorize_transactions(transactions: list[dict]) -> dict:
    """
    Categorize transactions and build a player acquisition history.

    Returns dict: player_key -> list of acquisition events
    """
    player_history = {}  # player_key -> list of events

    for tx in transactions:
        for p in tx["players"]:
            pk = p["player_key"]
            if pk not in player_history:
                player_history[pk] = []

            event = {
                "transaction_id": tx["transaction_id"],
                "type": tx["type"],
                "timestamp": tx["timestamp"],
                "transaction_type": p["transaction_type"],  # add/drop/trade
                "source_type": p["source_type"],
                "destination_type": p["destination_type"],
                "source_team_key": p["source_team_key"],
                "destination_team_key": p["destination_team_key"],
                "source_team_name": p["source_team_name"],
                "destination_team_name": p["destination_team_name"],
                "faab_bid": tx["faab_bid"],
                "player_name": p["name"],
            }
            player_history[pk].append(event)

    return player_history


def main():
    client = YahooFantasyClient()

    print("Fetching 2025 transactions...")
    transactions = fetch_all_transactions(client)
    print(f"Total transactions: {len(transactions)}")

    # Count by type
    from collections import Counter
    type_counts = Counter(tx["type"] for tx in transactions)
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    # Build player history
    player_history = categorize_transactions(transactions)
    print(f"\nPlayers with transaction history: {len(player_history)}")

    # Get team mapping
    teams = client.get_teams(league_key=LEAGUE_KEY_2025)
    team_map = {t["team_key"]: t["manager"] for t in teams}

    # Summarize: for each "no_contract" player, find their acquisition
    matched_file = Path("data/matched_2025_rosters.json")
    with open(matched_file, encoding="utf-8") as f:
        matched_data = json.load(f)

    resolved_count = 0
    unresolved = []

    for mgr_name, team_data in matched_data.items():
        no_contract = team_data.get("no_contract", [])
        if not no_contract:
            continue

        print(f"\n{'='*60}")
        print(f"{mgr_name} - No contract players resolution:")
        print(f"{'='*60}")

        for p in no_contract:
            player_name = p["name"]
            # Find player_key from yahoo roster
            yahoo_file = Path("data/yahoo_2025_rosters.json")
            with open(yahoo_file, encoding="utf-8") as f:
                yahoo_data = json.load(f)

            player_key = None
            for tk, td in yahoo_data.items():
                if td["manager"] == mgr_name:
                    for yp in td["players"]:
                        if yp["name"] == player_name:
                            player_key = yp.get("player_key", "")
                            break
                    break

            if player_key and player_key in player_history:
                history = player_history[player_key]
                # Find the most recent "add" event to this team
                adds = [
                    e for e in history
                    if e["transaction_type"] == "add"
                ]
                if adds:
                    latest_add = adds[-1]  # most recent
                    src = latest_add["source_type"]
                    faab = latest_add["faab_bid"]
                    tx_type = latest_add["type"]

                    if tx_type == "trade":
                        src_mgr = team_map.get(latest_add["source_team_key"], "?")
                        print(f"  TRADE    {player_name:30s} from {src_mgr}")
                    elif src in ("freeagents", "waivers"):
                        faab_str = f"FAAB ${faab}" if faab is not None else "FA $0"
                        print(f"  FAAB/FA  {player_name:30s} {faab_str}")
                    else:
                        print(f"  OTHER    {player_name:30s} src={src} type={tx_type}")
                    resolved_count += 1
                else:
                    print(f"  ???      {player_name:30s} (has history but no 'add')")
                    unresolved.append(player_name)
            else:
                print(f"  ???      {player_name:30s} (no transaction history)")
                unresolved.append(player_name)

    print(f"\n{'='*60}")
    print(f"Resolved: {resolved_count}, Unresolved: {len(unresolved)}")
    if unresolved:
        print("Unresolved players:")
        for name in unresolved:
            print(f"  - {name}")

    # Save full data
    save_data = {
        "transactions": transactions,
        "player_history": player_history,
    }
    output_file = Path("data/yahoo_2025_transactions.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
