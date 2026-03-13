"""
Seed 2026 buyout records for mid-season N-contract drops.

These players had N contracts in 2025 but were dropped during the season.
Per league rules, the original team must pay buyout costs.

Buyout calculation:
  - N1: remaining_years = 2 (N1 + O), buyout_years = 2 - 1 = 1
  - N2: remaining_years = 3 (N2 + N1 + O), buyout_years = 3 - 1 = 2

Usage:
  python scripts/seed_2026_buyouts.py
"""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from api.database import get_db, get_all_teams, create_buyout, _fetchall


def seed_buyouts():
    """Seed 2026 buyout records."""
    # Get team mapping
    teams = get_all_teams()
    team_map = {t["manager_name"]: t["id"] for t in teams}

    # 2026 buyout records (mid-season drops from 2025 N-contract players)
    buyouts = [
        {
            "manager": "rawstuff",
            "player_name": "Justin Steele",
            "original_contract": "$6/N1",
            "salary": 6,
            "n_years": 1,  # N1
            "notes": "2025 mid-season drop (N1 contract)",
        },
        {
            "manager": "YWC",
            "player_name": "Yanier Diaz",
            "original_contract": "$11/N2",
            "salary": 11,
            "n_years": 2,  # N2
            "notes": "2025 mid-season drop (N2 contract)",
        },
        {
            "manager": "Hyper",
            "player_name": "Zach Eflin",
            "original_contract": "$7/N1",
            "salary": 7,
            "n_years": 1,  # N1
            "notes": "2025 mid-season drop (N1 contract)",
        },
    ]

    created = 0
    skipped = 0

    for bo in buyouts:
        team_id = team_map.get(bo["manager"])
        if not team_id:
            print(f"[SKIP] Team not found: {bo['manager']}")
            skipped += 1
            continue

        # Check if already exists
        conn = get_db()
        try:
            existing = _fetchall(
                conn,
                """SELECT id FROM buyouts
                   WHERE team_id = %s AND player_name = %s AND year = 2026""",
                (team_id, bo["player_name"]),
            )
        finally:
            conn.close()

        if existing:
            print(f"[SKIP] Already exists: {bo['player_name']} ({bo['manager']})")
            skipped += 1
            continue

        # Calculate buyout years:
        # N(x) has remaining_years = x + 1 (N years + O year)
        # Buyout years = remaining_years - 1
        remaining_contract = bo["n_years"] + 1  # N years + O year
        buyout_years = remaining_contract - 1

        result = create_buyout(
            team_id=team_id,
            year=2026,
            player_name=bo["player_name"],
            original_contract=bo["original_contract"],
            buyout_salary=bo["salary"],
            buyout_faab=0,
            buyout_years=buyout_years,
            remaining_years=buyout_years,
            buyout_type="mid_season_drop",
            use_faab=False,
            notes=bo["notes"],
        )
        print(f"[OK] Created: {bo['player_name']} ({bo['manager']}) "
              f"- ${bo['salary']}/yr x {buyout_years}yr buyout")
        created += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}")


if __name__ == "__main__":
    seed_buyouts()
