"""
Fix trade_keeper players missing contract_type, salary, extension_years in JSON.
One-time script to patch data/2026_contracts_v2.json.
"""
import json
import re
import sys
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "2026_contracts_v2.json"


def parse_contract(contract_str: str):
    """Parse contract string like '$51/N7', 'A/$1', '$3/B', '$39/O'."""
    if not contract_str:
        return ("", 0, 0)

    # Format: $salary/type
    m1 = re.match(r"\$(\d+)/([A-Z]\d*)", contract_str)
    # Format: type/$salary
    m2 = re.match(r"([A-Z]\d*)/\$(\d+)", contract_str)

    if m1:
        salary = int(m1.group(1))
        ct = m1.group(2)
    elif m2:
        ct = m2.group(1)
        salary = int(m2.group(2))
    else:
        print(f"  WARNING: Cannot parse: {contract_str}", file=sys.stderr)
        return ("", 0, 0)

    # Extract type and extension years from e.g. "N7" -> ("N", 7)
    n_match = re.match(r"N(\d+)", ct)
    if n_match:
        return ("N", salary, int(n_match.group(1)))
    else:
        return (ct, salary, 0)


def fix_players_in_section(section: dict, fixed_count: int) -> int:
    """Fix trade_keeper players in a dict of team_id -> team_data."""
    for team_id, team_data in section.items():
        if not isinstance(team_data, dict):
            continue
        for cat in ["matched", "draft_new", "no_contract", "players"]:
            for p in team_data.get(cat, []):
                if p.get("source") != "trade_keeper":
                    continue
                c2025 = p.get("contract_2025", "")
                ct, sal, ext = parse_contract(c2025)
                changed = False
                if "contract_type" not in p or p.get("contract_type") == "":
                    p["contract_type"] = ct
                    changed = True
                if "salary" not in p or p.get("salary") == 0:
                    p["salary"] = sal
                    changed = True
                if "extension_years" not in p:
                    p["extension_years"] = ext
                    changed = True
                if changed:
                    fixed_count += 1
                    print(
                        f"  Fixed: {p['name']:25s} | "
                        f"type={p['contract_type']}, "
                        f"salary={p['salary']}, "
                        f"ext={p['extension_years']}"
                    )
    return fixed_count


def main():
    print(f"Reading {DATA_FILE} ...")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    fixed = 0

    # Fix in season_mapping / current_mapping sections
    for section_name in ["season_mapping", "current_mapping"]:
        section = data.get(section_name, {})
        if section:
            print(f"\nChecking [{section_name}] ...")
            fixed = fix_players_in_section(section, fixed)

    # Fix in teams section
    teams = data.get("teams", {})
    if teams:
        print("\nChecking [teams] ...")
        fixed = fix_players_in_section(teams, fixed)

    if fixed > 0:
        print(f"\nWriting back {fixed} fixes ...")
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Done!")
    else:
        print("\nNo fixes needed.")


if __name__ == "__main__":
    main()
