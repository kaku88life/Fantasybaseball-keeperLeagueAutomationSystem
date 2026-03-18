"""Re-fetch 2023 Yahoo transactions with pagination to skip bad player keys."""
import json
import time
from pathlib import Path

from src.api.yahoo_client import YahooFantasyClient

DATA_DIR = Path("data")
LEAGUE_KEY = "422.l.25091"  # 2023


def _parse_player(p_raw):
    """Parse a player from transaction data."""
    info_list = p_raw[0] if isinstance(p_raw, list) else []
    tx_data_raw = p_raw[1] if isinstance(p_raw, list) and len(p_raw) > 1 else {}

    player = {
        "name": "", "player_key": "", "position": "", "editorial_team": "",
        "transaction_type": "", "source_type": "", "destination_type": "",
        "source_team_key": "", "destination_team_key": "",
        "source_team_name": "", "destination_team_name": "",
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
        items = td if isinstance(td, list) else [td]
        for item in items:
            if isinstance(item, dict):
                for key in ("type", "source_type", "destination_type",
                            "source_team_key", "destination_team_key",
                            "source_team_name", "destination_team_name"):
                    if key in item:
                        field = "transaction_type" if key == "type" else key
                        player[field] = item[key]

    return player


def _parse_batch(tx_data, count):
    """Parse a batch of transactions from Yahoo API response."""
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
            "faab_bid": int(meta["faab_bid"]) if "faab_bid" in meta else None,
            "players": [],
        }

        if "players" in players_section:
            pd = players_section["players"]
            p_count = pd.get("count", 0)
            for j in range(p_count):
                player = _parse_player(pd[str(j)]["player"])
                tx_entry["players"].append(player)

        transactions.append(tx_entry)
    return transactions


def main():
    client = YahooFantasyClient()
    all_transactions = []
    batch_size = 25
    start = 0
    skipped = 0

    print(f"Fetching 2023 transactions (league: {LEAGUE_KEY})...")

    while True:
        try:
            data = client._get(
                f"/league/{LEAGUE_KEY}/transactions;start={start};count={batch_size}"
            )
            league_data = data["fantasy_content"]["league"]
            # Handle end-of-list: league may be a flat list without transactions
            if len(league_data) < 2 or not isinstance(league_data[1], dict):
                break
            tx_data = league_data[1].get("transactions", {})
            if not isinstance(tx_data, dict):
                break
            count = tx_data.get("count", 0)
            if count == 0:
                break

            batch = _parse_batch(tx_data, count)
            all_transactions.extend(batch)
            print(f"  {start}-{start + count}: {count} txs OK")
            start += batch_size
            time.sleep(0.3)

        except RuntimeError as e:
            if "does not exist" in str(e):
                print(f"  {start}-{start + batch_size}: bad player, fetching one-by-one...")
                for sub in range(batch_size):
                    try:
                        data = client._get(
                            f"/league/{LEAGUE_KEY}/transactions;start={start + sub};count=1"
                        )
                        tx_data = data["fantasy_content"]["league"][1]["transactions"]
                        count = tx_data.get("count", 0)
                        if count == 0:
                            break

                        batch = _parse_batch(tx_data, count)
                        all_transactions.extend(batch)

                    except RuntimeError:
                        skipped += 1
                        print(f"    index {start + sub}: SKIPPED (bad player key)")

                    time.sleep(0.2)

                start += batch_size
            else:
                print(f"  ERROR: {str(e)[:120]}")
                break

    # Build player history
    player_history: dict[str, list] = {}
    for tx in all_transactions:
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

    result = {"transactions": all_transactions, "player_history": player_history}

    out_path = DATA_DIR / "yahoo_2023_transactions.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Stats
    faab_count = sum(1 for t in all_transactions if t.get("faab_bid") and t["faab_bid"] > 0)
    trade_count = sum(1 for t in all_transactions if t.get("type") == "trade")
    print(f"\nDone! {len(all_transactions)} transactions saved ({skipped} skipped)")
    print(f"  Trades: {trade_count}, FAAB pickups: {faab_count}")


if __name__ == "__main__":
    main()
