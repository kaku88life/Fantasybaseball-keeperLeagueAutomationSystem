"""Analyze all players' contract data structure."""
import json

with open("data/2026_contracts_v2.json", "r") as f:
    data = json.load(f)

from collections import Counter

ct_counts = Counter()
all_players = []

for team_id, team_data in data["teams"].items():
    players_list = team_data if isinstance(team_data, list) else team_data.get("players", [])
    for p in players_list:
        if isinstance(p, dict):
            ct = p.get("contract_type", "?")
            ct_counts[ct] += 1
            all_players.append({**p, "team": team_id})

print("Contract type counts:")
for ct, count in sorted(ct_counts.items()):
    print(f"  {ct}: {count}")
print(f"Total: {sum(ct_counts.values())}")

# Show first player per contract type
print("\nSample players by contract type:")
seen = set()
for p in all_players:
    ct = p.get("contract_type", "?")
    if ct not in seen:
        seen.add(ct)
        print(f"  [{ct}] {p.get('name', '?')} | {p.get('position', '?')} | ${p.get('salary', 0)} | team={p.get('team', '?')}")
        print(f"        keys: {list(p.keys())}")
