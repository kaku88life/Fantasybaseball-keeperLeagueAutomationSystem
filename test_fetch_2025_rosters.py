"""Fetch all 16 teams' end-of-season 2025 rosters from Yahoo Fantasy API."""
import json
from src.api.yahoo_client import YahooFantasyClient

client = YahooFantasyClient()
league_key_2025 = "458.l.40288"

teams = client.get_teams(league_key=league_key_2025)
print(f"2025 League: {league_key_2025}")
print(f"Teams: {len(teams)}\n")

all_rosters = {}

for t in teams:
    team_key = t["team_key"]
    manager = t["manager"]
    team_name = t["name"]

    try:
        roster = client.get_roster(team_key)
        all_rosters[team_key] = {
            "manager": manager,
            "team_name": team_name,
            "team_key": team_key,
            "players": roster,
        }
        print(f"{manager:15s} | {team_name:25s} | {len(roster):2d} players")
        for p in roster:
            pos = p["position"]
            name = p["name"]
            mlb_team = p["team"]
            sel_pos = p["selected_position"]
            status = p.get("status", "")
            status_str = f" [{status}]" if status else ""
            print(f"  {sel_pos:4s} {pos:10s} {name:30s} ({mlb_team}){status_str}")
        print()
    except Exception as e:
        print(f"{manager:15s} | ERROR: {e}\n")

# Save to file for reference
output_file = "data/yahoo_2025_rosters.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_rosters, f, indent=2, ensure_ascii=False)
print(f"\nSaved to {output_file}")
