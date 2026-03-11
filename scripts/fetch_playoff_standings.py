"""
Fetch playoff scoreboard from Yahoo Fantasy API and compute final standings (1st-8th).

Usage:
    python -m scripts.fetch_playoff_standings [--year 2025] [--save]
    python -m scripts.fetch_playoff_standings --year 2025 --weeks 23,24,25 --save

Playoff bracket (8 teams, 3 weeks, default weeks from config/settings.py):
    Week 1 (QF): #1v#8, #2v#7, #3v#6, #4v#5  (4 matchups)
    Week 2 (SF): Winner's bracket SF + Consolation SF  (4 matchups)
    Week 3 (Finals): Championship + 3rd + 5th + 7th place games  (4 matchups)

Output: 1st-8th place standings with ranking bonus assignment (#1-#6 get bonus).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PLAYOFF_WEEKS, RANKING_BONUS
from src.api.yahoo_client import YahooFantasyClient


def fetch_playoff_matchups(
    client: YahooFantasyClient, year: int, weeks: list[int] | None = None
) -> dict:
    """Fetch scoreboard for all playoff weeks."""
    # Get the league key for the target year
    league_key = client.get_league_key(year)
    print(f"[Info] League key for {year}: {league_key}")

    playoff_weeks = weeks or PLAYOFF_WEEKS

    all_matchups = {}
    for week in playoff_weeks:
        print(f"[Fetch] Week {week} scoreboard...")
        try:
            matchups = client.get_scoreboard(week, league_key=league_key)
        except Exception as e:
            print(f"  [Error] Failed to fetch week {week}: {e}")
            continue
        # Only keep playoff (non-consolation) matchups
        playoff_matchups = [
            m for m in matchups
            if m["is_playoffs"] and not m["is_consolation"]
        ]
        all_matchups[week] = playoff_matchups
        print(f"  -> {len(playoff_matchups)} playoff matchups, "
              f"{len(matchups) - len(playoff_matchups)} consolation/regular matchups")

    return all_matchups


def compute_standings(all_matchups: dict) -> list[dict]:
    """
    Compute playoff standings 1st-8th from 3 weeks of matchup data.

    Yahoo marks ALL 8-team playoff matchups as is_playoffs=true (no consolation flag).
    We distinguish winner's bracket vs consolation bracket by tracking QF results:

    Logic:
        QF (Week 1): 4 matchups -> 4 winners (winner's bracket), 4 losers (consolation)
        SF (Week 2): Winner's bracket SF (2 matchups) + Consolation SF (2 matchups)
        Finals (Week 3): Championship + 3rd place + 5th place + 7th place

    Winner's bracket determines #1-#4, consolation determines #5-#8.
    Only #1-#6 get ranking bonus.
    """
    weeks = sorted(all_matchups.keys())
    if len(weeks) < 3:
        print(f"[Error] Expected 3 playoff weeks, got {len(weeks)}: {weeks}")
        return []

    qf_week, sf_week, finals_week = weeks[0], weeks[1], weeks[2]

    # ---- Helper to extract winner/loser from matchup ----
    def split_matchup(m):
        t1, t2 = m["teams"][0], m["teams"][1]
        if t1["is_winner"]:
            return t1, t2
        return t2, t1

    # ---- QF: Identify winners (-> winner's bracket) and losers (-> consolation) ----
    qf_matchups = all_matchups[qf_week]
    print(f"\n=== Week {qf_week} - Quarterfinals ({len(qf_matchups)} matchups) ===")

    qf_winner_keys = set()
    qf_loser_keys = set()

    for m in qf_matchups:
        if len(m["teams"]) != 2:
            print(f"  [Warning] Matchup has {len(m['teams'])} teams, skipping")
            continue
        winner, loser = split_matchup(m)
        qf_winner_keys.add(winner["team_key"])
        qf_loser_keys.add(loser["team_key"])
        print(f"  {winner['manager']} ({winner['name']}) {winner['points']} vs "
              f"{loser['points']} {loser['manager']} ({loser['name']})  "
              f"-> Winner: {winner['manager']}")

    # ---- SF: Split into winner's bracket and consolation by QF results ----
    sf_matchups = all_matchups[sf_week]
    print(f"\n=== Week {sf_week} - Semifinals ({len(sf_matchups)} matchups) ===")

    wb_sf_winners = []  # Winner's bracket SF winners -> Championship
    wb_sf_losers = []   # Winner's bracket SF losers -> 3rd place game
    con_sf_winners = [] # Consolation SF winners -> 5th place game
    con_sf_losers = []  # Consolation SF losers -> 7th place game

    for m in sf_matchups:
        if len(m["teams"]) != 2:
            continue
        winner, loser = split_matchup(m)
        t1_key, t2_key = m["teams"][0]["team_key"], m["teams"][1]["team_key"]

        # Determine bracket by checking if teams were QF winners or losers
        is_winners_bracket = (t1_key in qf_winner_keys or t2_key in qf_winner_keys)

        if is_winners_bracket:
            wb_sf_winners.append(winner)
            wb_sf_losers.append(loser)
            bracket_label = "Winner's Bracket"
        else:
            con_sf_winners.append(winner)
            con_sf_losers.append(loser)
            bracket_label = "Consolation"

        print(f"  [{bracket_label}] {winner['manager']} {winner['points']} vs "
              f"{loser['points']} {loser['manager']}  -> Winner: {winner['manager']}")

    # ---- Finals: Assign places based on bracket ----
    finals_matchups = all_matchups[finals_week]
    print(f"\n=== Week {finals_week} - Finals ({len(finals_matchups)} matchups) ===")

    standings = {}  # team_key -> {place, manager, name, ...}

    wb_sf_winner_keys = {w["team_key"] for w in wb_sf_winners}
    wb_sf_loser_keys = {l["team_key"] for l in wb_sf_losers}
    con_sf_winner_keys = {w["team_key"] for w in con_sf_winners}
    con_sf_loser_keys = {l["team_key"] for l in con_sf_losers}

    for m in finals_matchups:
        if len(m["teams"]) != 2:
            continue
        winner, loser = split_matchup(m)
        t1_key, t2_key = m["teams"][0]["team_key"], m["teams"][1]["team_key"]

        # Championship game (Winner's bracket SF winners)
        if t1_key in wb_sf_winner_keys or t2_key in wb_sf_winner_keys:
            place_w, place_l, label = 1, 2, "Championship"
        # 3rd place game (Winner's bracket SF losers)
        elif t1_key in wb_sf_loser_keys or t2_key in wb_sf_loser_keys:
            place_w, place_l, label = 3, 4, "3rd Place"
        # 5th place game (Consolation SF winners)
        elif t1_key in con_sf_winner_keys or t2_key in con_sf_winner_keys:
            place_w, place_l, label = 5, 6, "5th Place"
        # 7th place game (Consolation SF losers)
        elif t1_key in con_sf_loser_keys or t2_key in con_sf_loser_keys:
            place_w, place_l, label = 7, 8, "7th Place"
        else:
            print(f"  [Warning] Unknown matchup: {winner['manager']} vs {loser['manager']}")
            continue

        standings[winner["team_key"]] = {
            "place": place_w, "manager": winner["manager"],
            "name": winner["name"], "team_key": winner["team_key"],
        }
        standings[loser["team_key"]] = {
            "place": place_l, "manager": loser["manager"],
            "name": loser["name"], "team_key": loser["team_key"],
        }
        print(f"  [{label}] {winner['manager']} {winner['points']} vs "
              f"{loser['points']} {loser['manager']}  "
              f"-> #{place_w}: {winner['manager']}, #{place_l}: {loser['manager']}")

    # ---- Build final results ----
    results = sorted(standings.values(), key=lambda x: x["place"])

    print(f"\n{'='*50}")
    print(f"  FINAL PLAYOFF STANDINGS")
    print(f"{'='*50}")
    for r in results:
        bonus = RANKING_BONUS.get(r["place"], 0)
        bonus_str = f"+${bonus}" if bonus > 0 else "---"
        crown = " (crown)" if r["place"] == 1 else ""
        print(f"  #{r['place']}: {r['manager']} ({r['name']}) "
              f"  Bonus: {bonus_str}{crown}")

    return results


def save_results(results: list[dict], year: int):
    """Save playoff standings to a JSON file."""
    output_path = Path(__file__).resolve().parent.parent / "data" / f"{year}_playoff_standings.json"
    output = {
        "year": year,
        "playoff_weeks": PLAYOFF_WEEKS,
        "standings": results,
        "ranking_bonus_map": {
            r["manager"]: RANKING_BONUS.get(r["place"], 0)
            for r in results
        },
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[Saved] {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Fetch playoff standings from Yahoo API")
    parser.add_argument("--year", type=int, default=2025, help="Season year (default: 2025)")
    parser.add_argument("--weeks", type=str, default=None,
                        help="Override playoff weeks, comma-separated (e.g., '23,24,25')")
    parser.add_argument("--save", action="store_true", help="Save results to JSON file")
    args = parser.parse_args()

    weeks = None
    if args.weeks:
        weeks = [int(w.strip()) for w in args.weeks.split(",")]

    effective_weeks = weeks or PLAYOFF_WEEKS
    print(f"[Start] Fetching {args.year} playoff standings...")
    print(f"[Config] Playoff weeks: {effective_weeks}")

    client = YahooFantasyClient()
    all_matchups = fetch_playoff_matchups(client, args.year, weeks=weeks)
    results = compute_standings(all_matchups)

    if not results:
        print("[Error] Could not compute standings.")
        sys.exit(1)

    if args.save:
        save_results(results, args.year)

    # Print summary for easy copy
    print(f"\n--- Ranking Bonus Summary (for {args.year + 1} season) ---")
    for r in results:
        bonus = RANKING_BONUS.get(r["place"], 0)
        if bonus > 0:
            print(f"  {r['manager']}: +${bonus} (#{r['place']})")


if __name__ == "__main__":
    main()
