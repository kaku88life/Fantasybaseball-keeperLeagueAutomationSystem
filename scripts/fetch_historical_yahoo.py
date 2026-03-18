"""
Fetch historical Yahoo Fantasy data for years 2022-2024.

Retrieves draft results, transactions, and rosters for analytics.
Saves to data/yahoo_{year}_draft.json and data/yahoo_{year}_transactions.json.
"""
import json
import time
from pathlib import Path

from src.api.yahoo_client import YahooFantasyClient

DATA_DIR = Path("data")


def fetch_draft_with_players(client: YahooFantasyClient, league_key: str, year: int) -> list[dict]:
    """Fetch draft results and enrich with player names."""
    print(f"  Fetching draft results...")
    results = client.get_draft_results(league_key=league_key)
    print(f"  Got {len(results)} picks")

    if not results:
        return []

    # Get team mapping
    teams = client.get_teams(league_key=league_key)
    team_map = {t["team_key"]: t["manager"] for t in teams}

    # Collect all player keys for batch lookup
    player_keys = [r["player_key"] for r in results if r.get("player_key")]

    # Batch lookup player names (Yahoo API supports up to 25 at a time)
    player_names = {}
    batch_size = 25
    for i in range(0, len(player_keys), batch_size):
        batch = player_keys[i:i + batch_size]
        keys_str = ",".join(batch)
        try:
            data = client._get(f"/players;player_keys={keys_str}")
            players_data = data.get("fantasy_content", {}).get("players", {})
            count = players_data.get("count", 0)
            for j in range(count):
                p_raw = players_data[str(j)]["player"][0]
                p_key = ""
                p_name = ""
                p_pos = ""
                p_team = ""
                for item in p_raw:
                    if isinstance(item, dict):
                        if "player_key" in item:
                            p_key = item["player_key"]
                        if "name" in item:
                            p_name = item["name"].get("full", "")
                        if "display_position" in item:
                            p_pos = item["display_position"]
                        if "editorial_team_abbr" in item:
                            p_team = item["editorial_team_abbr"]
                player_names[p_key] = {
                    "name": p_name,
                    "position": p_pos,
                    "team": p_team,
                }
        except Exception as e:
            print(f"  Warning: batch player lookup failed: {e}")

        # Rate limiting
        time.sleep(0.5)

    # Enrich draft results
    enriched = []
    for pick in results:
        pk = pick.get("player_key", "")
        p_info = player_names.get(pk, {})
        enriched.append({
            "round": pick["round"],
            "pick": pick["pick"],
            "player_key": pk,
            "player_name": p_info.get("name", ""),
            "position": p_info.get("position", ""),
            "editorial_team": p_info.get("team", ""),
            "cost": pick["cost"],
            "team_key": pick["team_key"],
            "manager": team_map.get(pick["team_key"], "Unknown"),
        })

    return enriched


def fetch_transactions_full(client: YahooFantasyClient, league_key: str, year: int) -> dict:
    """Fetch all transactions with full player details (reuses fetch_transactions.py logic)."""
    print(f"  Fetching transactions...")

    try:
        data = client._get(f"/league/{league_key}/transactions")
    except RuntimeError as e:
        print(f"  Warning: transactions fetch failed: {e}")
        return {"transactions": [], "player_history": {}}

    tx_data = data["fantasy_content"]["league"][1]["transactions"]
    count = tx_data.get("count", 0)
    print(f"  Got {count} transactions")

    # Get team mapping
    teams = client.get_teams(league_key=league_key)
    team_map = {t["team_key"]: t["manager"] for t in teams}

    transactions = []
    for i in range(count):
        tx_raw = tx_data[str(i)]["transaction"]
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

        if "faab_bid" in meta:
            tx_entry["faab_bid"] = int(meta["faab_bid"])

        # Parse players
        if "players" in players_section:
            players_data = players_section["players"]
            p_count = players_data.get("count", 0)
            for j in range(p_count):
                p_raw = players_data[str(j)]["player"]
                player = _parse_tx_player(p_raw, team_map)
                tx_entry["players"].append(player)

        transactions.append(tx_entry)

    # Build player history
    player_history = {}
    for tx in transactions:
        for p in tx["players"]:
            pk = p.get("player_key", "")
            if not pk:
                continue
            if pk not in player_history:
                player_history[pk] = []
            player_history[pk].append({
                "transaction_id": tx["transaction_id"],
                "type": tx["type"],
                "timestamp": tx["timestamp"],
                "transaction_type": p.get("transaction_type", ""),
                "source_type": p.get("source_type", ""),
                "destination_type": p.get("destination_type", ""),
                "source_team_key": p.get("source_team_key", ""),
                "destination_team_key": p.get("destination_team_key", ""),
                "source_team_name": p.get("source_team_name", ""),
                "destination_team_name": p.get("destination_team_name", ""),
                "faab_bid": tx["faab_bid"],
                "player_name": p.get("name", ""),
            })

    return {"transactions": transactions, "player_history": player_history}


def _parse_tx_player(player_raw, team_map: dict) -> dict:
    """Parse a player from a transaction entry."""
    info_list = player_raw[0] if isinstance(player_raw, list) else []
    tx_data_raw = player_raw[1] if isinstance(player_raw, list) and len(player_raw) > 1 else {}

    player = {
        "name": "",
        "player_key": "",
        "position": "",
        "editorial_team": "",
        "transaction_type": "",
        "source_type": "",
        "destination_type": "",
        "source_team_key": "",
        "destination_team_key": "",
        "source_team_name": "",
        "destination_team_name": "",
    }

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

    if isinstance(tx_data_raw, dict) and "transaction_data" in tx_data_raw:
        td = tx_data_raw["transaction_data"]
        if isinstance(td, list):
            for item in td:
                if isinstance(item, dict):
                    _extract_td(item, player)
        elif isinstance(td, dict):
            _extract_td(td, player)

    return player


def _extract_td(td: dict, player: dict):
    """Extract transaction data fields."""
    for key in ("type", "source_type", "destination_type",
                "source_team_key", "destination_team_key",
                "source_team_name", "destination_team_name"):
        if key in td:
            field = "transaction_type" if key == "type" else key
            player[field] = td[key]


def main():
    client = YahooFantasyClient()

    # Discover all available league keys
    print("Discovering league keys...")
    league_keys = client.discover_league_keys()
    print(f"Found leagues: {league_keys}")

    # Target years to fetch (skip years we already have)
    target_years = []
    for year in sorted(league_keys.keys()):
        draft_file = DATA_DIR / f"yahoo_{year}_draft.json"
        tx_file = DATA_DIR / f"yahoo_{year}_transactions.json"
        if draft_file.exists() and tx_file.exists():
            print(f"\n{year}: Already have data, skipping")
            continue
        if year >= 2026:
            print(f"\n{year}: Current/future season, skipping")
            continue
        target_years.append(year)

    if not target_years:
        print("\nNo new years to fetch!")
        return

    print(f"\nWill fetch data for: {target_years}")

    for year in target_years:
        league_key = league_keys[year]
        print(f"\n{'='*60}")
        print(f"  {year} season (league_key: {league_key})")
        print(f"{'='*60}")

        # Fetch draft
        draft_file = DATA_DIR / f"yahoo_{year}_draft.json"
        if not draft_file.exists():
            try:
                draft = fetch_draft_with_players(client, league_key, year)
                with open(draft_file, "w", encoding="utf-8") as f:
                    json.dump(draft, f, indent=2, ensure_ascii=False)
                print(f"  Saved draft: {draft_file} ({len(draft)} picks)")
            except Exception as e:
                print(f"  ERROR fetching draft: {e}")
        else:
            print(f"  Draft file exists, skipping")

        time.sleep(1)  # Rate limiting

        # Fetch transactions
        tx_file = DATA_DIR / f"yahoo_{year}_transactions.json"
        if not tx_file.exists():
            try:
                tx_data = fetch_transactions_full(client, league_key, year)
                with open(tx_file, "w", encoding="utf-8") as f:
                    json.dump(tx_data, f, indent=2, ensure_ascii=False)
                tx_count = len(tx_data.get("transactions", []))
                print(f"  Saved transactions: {tx_file} ({tx_count} transactions)")
            except Exception as e:
                print(f"  ERROR fetching transactions: {e}")
        else:
            print(f"  Transactions file exists, skipping")

        time.sleep(1)  # Rate limiting between years

    print(f"\n{'='*60}")
    print("Done! Check data/ directory for new files.")


if __name__ == "__main__":
    main()
