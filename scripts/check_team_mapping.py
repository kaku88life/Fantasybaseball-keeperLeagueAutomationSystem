"""
Check if team_key -> manager mapping is consistent between
transactions and rosters. Maybe managers swapped teams.
"""
import json
from datetime import datetime

with open("data/yahoo_2025_rosters.json", encoding="utf-8") as f:
    rosters = json.load(f)
with open("data/yahoo_2025_transactions.json", encoding="utf-8") as f:
    tx_data = json.load(f)

# Current roster: team_key -> manager
print("=" * 60)
print("ROSTER DATA: team_key -> manager")
print("=" * 60)
for tk, td in sorted(rosters.items()):
    print(f"  {tk:25s} -> {td['manager']}")

# From transactions: check what manager names appear for each team_key
print()
print("=" * 60)
print("TRANSACTION DATA: team_key -> team_names used")
print("=" * 60)

team_key_names = {}
for tx in tx_data["transactions"]:
    for p in tx["players"]:
        for field, name_field in [
            ("source_team_key", "source_team_name"),
            ("destination_team_key", "destination_team_name"),
        ]:
            tk = p.get(field, "")
            tn = p.get(name_field, "")
            if tk and tn:
                if tk not in team_key_names:
                    team_key_names[tk] = set()
                team_key_names[tk].add(tn)

for tk in sorted(team_key_names.keys()):
    roster_mgr = ""
    for rtk, rtd in rosters.items():
        if rtk == tk:
            roster_mgr = rtd["manager"]
            break
    names = team_key_names[tk]
    match = "OK" if any(roster_mgr in n or n in roster_mgr for n in names) else "MISMATCH?"
    print(f"  {tk:25s} | Roster: {roster_mgr:10s} | TX names: {names} | {match}")

# Specifically check the suspicious pairs
print()
print("=" * 60)
print("SUSPICIOUS PATTERN ANALYSIS")
print("=" * 60)

# Players traded to EDDIE (t.3) are on 叫我寬哥 (t.2)
# Players traded to 魚魚 (t.14) are on 謙謙 (t.13)
# Players traded to Billy (t.7) are on rawstuff (t.6)
# Players traded to TIMMY LIU (t.12) are on Hyper (t.11)
patterns = [
    ("EDDIE (t.3)", "叫我寬哥 (t.2)", 3, 2),
    ("魚魚 (t.14)", "謙謙 (t.13)", 14, 13),
    ("Billy (t.7)", "rawstuff (t.6)", 7, 6),
    ("TIMMY LIU (t.12)", "Hyper (t.11)", 12, 11),
    ("叫我寬哥 (t.2)", "Leo (t.16)", 2, 16),
    ("Ponpon (t.15)", "魚魚 (t.14)", 15, 14),
    ("YWC (t.8)", "Billy (t.7)", 8, 7),
]

print("Trade destination -> Actual team | team# difference")
for label_from, label_to, num_from, num_to in patterns:
    diff = num_from - num_to
    print(f"  {label_from:20s} -> {label_to:20s} | diff: {diff:+d}")

# Check: maybe there's a systematic shift?
# t.3 -> t.2 (diff -1)
# t.14 -> t.13 (diff -1)
# t.7 -> t.6 (diff -1)
# t.12 -> t.11 (diff -1)
# t.2 -> t.16 (diff -14??)
# t.15 -> t.14 (diff -1)
# t.8 -> t.7 (diff -1)

print()
print("Most patterns show diff = -1!")
print("This suggests the team numbering shifted by 1 between")
print("transaction data and roster data.")
