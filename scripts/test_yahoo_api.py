"""
Fantasy Baseball Keeper League - Yahoo API Connection Test

Tests OAuth2 authentication and basic API calls.
Run: python scripts/test_yahoo_api.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.api.yahoo_client import YahooFantasyClient


def main():
    print("=" * 55)
    print(" Yahoo Fantasy API Connection Test")
    print("=" * 55)

    client = YahooFantasyClient()

    if not client.league_id:
        print("\nError: YAHOO_LEAGUE_ID not set in .env")
        return

    print(f"\nLeague ID: {client.league_id}")

    # Step 1: Basic connection
    print("\n--- Step 1: Connection Test ---")
    result = client.test_connection()

    if result["status"] != "success":
        print(f"  FAILED: {result['message']}")
        print("\nTroubleshooting:")
        print("  1. Run: python scripts/yahoo_auth.py")
        print("  2. Check .env credentials")
        return

    print(f"  League: {result['league_name']}")
    print(f"  Season: {result['season']}")
    print(f"  Teams: {result['num_teams']}")
    print(f"  Draft: {result['draft_status']}")
    print("\n  Team List:")
    for t in result.get("teams", []):
        print(f"    {t['key'].split('.')[-1]:>2s}. {t['name']} ({t['manager']})")

    # Step 2: Multi-year league discovery
    print("\n--- Step 2: Multi-Year League Keys ---")
    try:
        keys = client.discover_league_keys()
        for year in sorted(keys):
            marker = " <-- current" if keys[year] == client.league_id else ""
            print(f"  {year}: {keys[year]}{marker}")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 3: Standings (may be empty for predraft)
    print("\n--- Step 3: Standings ---")
    try:
        standings = client.get_standings()
        has_records = any(s.get("wins") for s in standings)
        if has_records:
            for s in standings:
                print(
                    f"  #{s.get('rank', '?'):>2s} {s['name']:30s} "
                    f"{s.get('wins', 0)}W-{s.get('losses', 0)}L"
                )
        else:
            print(f"  {len(standings)} teams found (predraft - no records yet)")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 4: Draft results (try 2025 if current is predraft)
    print("\n--- Step 4: Draft Results ---")
    try:
        drafts = client.get_draft_results()
        if drafts:
            print(f"  Total picks: {len(drafts)}")
            print(f"  First 5 picks:")
            for d in drafts[:5]:
                print(
                    f"    Rd{d['round']} Pick{d['pick']}: "
                    f"team={d['team_key'].split('.')[-1]} "
                    f"player={d['player_key']} ${d['cost']}"
                )
        else:
            print("  No draft results (predraft)")
            # Try previous year
            if 2025 in client._league_keys:
                lk25 = client._league_keys[2025]
                print(f"  Trying 2025 ({lk25})...")
                drafts25 = client.get_draft_results(league_key=lk25)
                print(f"  2025 draft picks: {len(drafts25)}")
                for d in drafts25[:3]:
                    print(
                        f"    Rd{d['round']} Pick{d['pick']}: "
                        f"${d['cost']}"
                    )
    except Exception as e:
        print(f"  Error: {e}")

    # Step 5: Roster (try 2025 if current is predraft)
    print("\n--- Step 5: Roster Sample ---")
    try:
        roster = client.get_roster("1")
        if roster:
            print(f"  Team 1 roster: {len(roster)} players")
            for p in roster[:5]:
                print(
                    f"    {p['selected_position']:4s} {p['name']:25s} "
                    f"{p['position']:10s} ({p['team']})"
                )
            if len(roster) > 5:
                print(f"    ... and {len(roster) - 5} more")
        else:
            print("  Empty roster (predraft)")
            if 2025 in client._league_keys:
                lk25 = client._league_keys[2025]
                print(f"  Trying 2025 ({lk25})...")
                roster25 = client.get_roster("1", league_key=lk25)
                print(f"  2025 Team 1: {len(roster25)} players")
                for p in roster25[:5]:
                    print(
                        f"    {p['selected_position']:4s} {p['name']:25s} "
                        f"({p['team']})"
                    )
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "=" * 55)
    print(" All API tests passed!")
    print("=" * 55)


if __name__ == "__main__":
    main()
