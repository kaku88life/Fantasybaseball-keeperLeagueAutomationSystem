"""Check player source distribution."""
import json
from collections import Counter

with open("data/2026_contracts_v2.json", "r") as f:
    data = json.load(f)

source_counts = Counter()
source_examples = {}

for team_id, team_data in data["teams"].items():
    players_list = team_data if isinstance(team_data, list) else team_data.get("players", [])
    for p in players_list:
        if isinstance(p, dict):
            src = p.get("source", "unknown")
            source_counts[src] += 1
            if src not in source_examples:
                source_examples[src] = f"{p.get('name', '?')} ({p.get('contract_type', '?')}/{p.get('team', '?')})"

print("Source distribution:")
for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
    print(f"  {src:25s}: {count:>4d}  (e.g. {source_examples[src]})")
print(f"Total: {sum(source_counts.values())}")
