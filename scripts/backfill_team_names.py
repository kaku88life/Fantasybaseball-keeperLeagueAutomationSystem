"""Backfill teams.team_name from Yahoo-synced roster data.

Default source is the DB synced_rosters table, which is populated by the
Yahoo live roster sync. Local JSON is an explicit fallback only.

Usage:
    python -m scripts.backfill_team_names --year 2026
    python -m scripts.backfill_team_names --year 2026 --apply
    python -m scripts.backfill_team_names --year 2026 --source local-file
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_rosters(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Roster JSON not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Roster JSON must be an object: {path}")
    return data


def _load_synced_rosters(year: int) -> dict:
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL is not set, so DB synced_rosters cannot be read. "
            "Run the script in the deployed environment or pass --source local-file "
            "only for an explicit fallback."
        )

    from api.database import get_synced_roster

    rosters = get_synced_roster(year)
    if not rosters:
        raise RuntimeError(
            f"No synced_rosters data found for {year}. Run Yahoo roster sync first, "
            "then retry this backfill."
        )
    return rosters


def _extract_rows(rosters: dict) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    skipped: list[dict] = []
    for roster_key, team_data in rosters.items():
        if not isinstance(team_data, dict):
            skipped.append({"key": str(roster_key), "reason": "team payload is not a dict"})
            continue
        manager = str(team_data.get("manager") or "").strip()
        team_name = str(team_data.get("team_name") or "").strip()
        yahoo_team_id = str(team_data.get("team_key") or roster_key or "").strip()
        players = team_data.get("players") if isinstance(team_data.get("players"), list) else []
        if not manager or not team_name:
            skipped.append({
                "key": yahoo_team_id,
                "manager": manager,
                "team_name": team_name,
                "reason": "missing manager or team_name",
            })
            continue
        rows.append({
            "manager": manager,
            "team_name": team_name,
            "yahoo_team_id": yahoo_team_id,
            "players": len(players),
        })
    return rows, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill teams.team_name from Yahoo-synced roster data"
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--source",
        choices=("db-synced", "local-file"),
        default="db-synced",
        help=(
            "db-synced reads the roster payload saved by Yahoo live sync. "
            "local-file is an explicit fallback for development only."
        ),
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Override roster JSON path when --source local-file is used.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to database. Without this flag, only prints a dry-run preview.",
    )
    args = parser.parse_args()

    if args.source == "db-synced":
        source_label = f"DB synced_rosters year={args.year}"
        rosters = _load_synced_rosters(args.year)
    else:
        roster_path = args.path or (ROOT / "data" / f"yahoo_{args.year}_rosters.json")
        source_label = str(roster_path)
        rosters = _load_rosters(roster_path)

    rows, skipped = _extract_rows(rosters)

    print(f"Source: {source_label}")
    if args.source == "local-file":
        print("WARNING: local-file is a development fallback and may be stale.")
    print(f"Valid team rows: {len(rows)}")
    for row in sorted(rows, key=lambda r: r["manager"]):
        print(
            f"  {row['manager']:12s} | {row['team_name']:24s} | "
            f"{row['yahoo_team_id']} | {row['players']} players"
        )

    if skipped:
        print(f"\nSkipped: {len(skipped)}")
        for item in skipped:
            print(f"  {item}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write teams.team_name.")
        return 0

    from api.database import sync_team_names_from_rosters

    result = sync_team_names_from_rosters(rosters)
    print(
        "\nApplied backfill: "
        f"{result['upserted']} upserted, {len(result['skipped'])} skipped"
    )
    return 0 if result["upserted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
