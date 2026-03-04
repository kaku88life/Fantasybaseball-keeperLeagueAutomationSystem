"""
Fantasy Baseball Keeper League - Data Sync Test

Tests the integration between Excel contract data and Yahoo API.
Run: python scripts/test_data_sync.py <excel_path> [--year 2025]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.import_excel import import_yearly_sheet, load_workbook
from src.api.data_sync import DataSync
from src.api.yahoo_client import YahooFantasyClient


def main():
    parser = argparse.ArgumentParser(description="Test data sync between Excel and Yahoo")
    parser.add_argument("filepath", help="Path to the Excel file")
    parser.add_argument("--year", type=int, default=2025, help="Year to sync (default: 2025)")
    args = parser.parse_args()

    print("=" * 60)
    print(f" Data Sync Test - {args.year} Season")
    print("=" * 60)

    # Step 1: Import Excel data
    print(f"\n--- Step 1: Loading Excel data ---")
    wb = load_workbook(args.filepath)
    sheet_name = f"{args.year}年選秀前名單"

    if sheet_name not in wb.sheetnames:
        print(f"Sheet '{sheet_name}' not found in Excel.")
        print(f"Available: {[s for s in wb.sheetnames if '選秀' in s]}")
        return

    excel_teams = import_yearly_sheet(wb[sheet_name], args.year)
    print(f"  Loaded {len(excel_teams)} teams from Excel")
    for t in excel_teams:
        print(f"    {t.manager_name}: {len(t.players)} keepers, "
              f"cost=${t.total_keeper_cost}")

    # Step 2: Connect Yahoo API
    print(f"\n--- Step 2: Connecting to Yahoo API ---")
    client = YahooFantasyClient()

    # Discover league keys
    print("  Discovering league keys...")
    keys = client.discover_league_keys()
    if args.year in keys:
        lk = keys[args.year]
        print(f"  Found: {args.year} -> {lk}")
    else:
        print(f"  No league found for {args.year}")
        print(f"  Available: {sorted(keys.keys())}")
        return

    # Step 3: Sync
    print(f"\n--- Step 3: Syncing data ---")
    sync = DataSync(client)
    result = sync.sync_league(excel_teams, args.year, league_key=lk)

    # Step 4: Report
    sync.print_sync_report(result)

    # Step 5: Sample enriched data
    print(f"\n--- Step 5: Enriched Player Sample ---")
    for tm in result["team_matches"][:3]:
        et = tm["excel_team"]
        print(f"\n  {et.manager_name}:")
        for p in et.players[:5]:
            yahoo_id = p.yahoo_player_id or "(no match)"
            print(f"    {p.name:25s} {p.contract.display:10s} "
                  f"pos={p.position:10s} yahoo={yahoo_id}")


if __name__ == "__main__":
    main()
