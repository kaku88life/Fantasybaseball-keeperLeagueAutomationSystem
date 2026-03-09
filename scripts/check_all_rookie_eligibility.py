"""
Check rookie eligibility for ALL players in the system via MLB Stats API.
Outputs a list of players who qualify for R contracts.
"""
import asyncio
import json
import sys
import time

import httpx

MLB_BASE = "https://statsapi.mlb.com/api/v1"
ROOKIE_IP_THRESHOLD = 50
ROOKIE_PA_THRESHOLD = 130
MAX_CONCURRENT = 10  # limit concurrent API calls


def parse_ip(ip_str):
    try:
        parts = str(ip_str).split(".")
        whole = int(parts[0])
        if len(parts) > 1:
            thirds = int(parts[1])
            return whole + thirds / 3.0
        return float(whole)
    except (ValueError, IndexError):
        return 0.0


async def search_player(client, sem, name, position):
    """Search for a player on MLB Stats API."""
    clean_name = name.split("(")[0].strip()
    async with sem:
        try:
            resp = await client.get(
                f"{MLB_BASE}/people/search",
                params={"names": clean_name, "hydrate": "currentTeam"},
            )
            resp.raise_for_status()
        except Exception:
            return None

    data = resp.json()
    rows = data.get("people", [])
    if not rows:
        return None

    best = rows[0]
    if len(rows) > 1 and position:
        is_pitcher = any(p in position.upper() for p in ("SP", "RP", "P"))
        for p in rows:
            pp = p.get("primaryPosition", {}).get("abbreviation", "")
            if is_pitcher and pp in ("P", "SP", "RP", "TWP"):
                best = p
                break
            elif not is_pitcher and pp not in ("P", "SP", "RP", "TWP"):
                best = p
                break

    return best


async def get_career_stats(client, sem, mlb_id):
    """Get career stats for a player."""
    async with sem:
        try:
            resp = await client.get(
                f"{MLB_BASE}/people/{mlb_id}/stats",
                params={"stats": "career", "group": "hitting,pitching"},
            )
            resp.raise_for_status()
        except Exception:
            return None
    return resp.json()


async def check_player(client, sem, player_info):
    """Check a single player's rookie eligibility."""
    name = player_info["name"]
    position = player_info["position"]

    player = await search_player(client, sem, name, position)
    if not player:
        # Not found in MLB = no MLB record = eligible
        return {
            **player_info,
            "found": False,
            "career_pa": 0,
            "career_ip": 0.0,
            "eligible": True,
            "reason": "no MLB record",
        }

    mlb_id = player["id"]
    stats_data = await get_career_stats(client, sem, mlb_id)
    if not stats_data:
        return {
            **player_info,
            "found": True,
            "mlb_name": player.get("fullName", name),
            "career_pa": 0,
            "career_ip": 0.0,
            "eligible": True,
            "reason": "no career stats",
        }

    career_pa = 0
    career_ip = 0.0

    for stat_group in stats_data.get("stats", []):
        group_name = stat_group.get("group", {}).get("displayName", "")
        for split in stat_group.get("splits", []):
            sport_id = split.get("sport", {}).get("id")
            if sport_id is not None and sport_id != 1:
                continue
            s = split.get("stat", {})
            if group_name == "hitting":
                career_pa = s.get("plateAppearances", 0)
            elif group_name == "pitching":
                career_ip = parse_ip(s.get("inningsPitched", "0.0"))

    exceeded_pa = career_pa > ROOKIE_PA_THRESHOLD
    exceeded_ip = career_ip > ROOKIE_IP_THRESHOLD
    eligible = not exceeded_pa and not exceeded_ip

    reason = ""
    if eligible:
        if career_pa == 0 and career_ip == 0.0:
            reason = "no MLB stats"
        else:
            parts = []
            if career_pa > 0:
                parts.append(f"PA={career_pa}/130")
            if career_ip > 0:
                parts.append(f"IP={career_ip}/50")
            reason = ", ".join(parts)
    else:
        parts = []
        if exceeded_pa:
            parts.append(f"PA={career_pa}>130")
        if exceeded_ip:
            parts.append(f"IP={career_ip}>50")
        reason = ", ".join(parts)

    return {
        **player_info,
        "found": True,
        "mlb_name": player.get("fullName", name),
        "career_pa": career_pa,
        "career_ip": round(career_ip, 1),
        "eligible": eligible,
        "exceeded_pa": exceeded_pa,
        "exceeded_ip": exceeded_ip,
        "reason": reason,
    }


async def main():
    # Load all players
    with open("data/2026_contracts_v2.json", "r") as f:
        data = json.load(f)

    all_players = []
    teams_data = data["teams"]
    for team_id, team_data in teams_data.items():
        players_list = team_data if isinstance(team_data, list) else team_data.get("players", [])
        for p in players_list:
            if isinstance(p, dict):
                all_players.append({
                    "name": p.get("name", ""),
                    "position": p.get("position", ""),
                    "team": team_id,
                    "contract_type": p.get("contract_type", ""),
                    "salary": p.get("salary", 0),
                })

    total = len(all_players)
    print(f"Checking {total} players against MLB Stats API...")
    print(f"(concurrency: {MAX_CONCURRENT}, estimated time: ~{total * 2 // MAX_CONCURRENT}s)")
    print()

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    start = time.time()

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Process in batches of 50
        results = []
        batch_size = 50
        for i in range(0, total, batch_size):
            batch = all_players[i : i + batch_size]
            batch_results = await asyncio.gather(
                *[check_player(client, sem, p) for p in batch],
                return_exceptions=True,
            )
            for r in batch_results:
                if isinstance(r, Exception):
                    results.append({"eligible": False, "error": str(r)})
                else:
                    results.append(r)
            done = min(i + batch_size, total)
            elapsed = time.time() - start
            print(f"  Progress: {done}/{total} ({elapsed:.0f}s)", flush=True)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")
    print()

    # Separate eligible vs not eligible
    eligible = [r for r in results if r.get("eligible")]
    not_eligible = [r for r in results if not r.get("eligible")]

    # Sort eligible by contract type (R first, then A, then others)
    ct_order = {"R": 0, "A": 1, "B": 2, "N": 3, "O": 4, "FA": 5}
    eligible.sort(key=lambda x: (ct_order.get(x.get("contract_type", ""), 9), x.get("team", ""), x.get("name", "")))

    print("=" * 100)
    print(f"ROOKIE ELIGIBLE PLAYERS: {len(eligible)} / {total}")
    print("=" * 100)
    print()

    # Group by contract type
    for ct_label, ct_code in [("R Contract (current rookies)", "R"), ("A Contract", "A"), ("B Contract", "B"), ("N Contract", "N"), ("O Contract", "O")]:
        ct_players = [r for r in eligible if r.get("contract_type") == ct_code]
        if not ct_players:
            continue
        print(f"--- {ct_label}: {len(ct_players)} eligible ---")
        for r in ct_players:
            name = r.get("mlb_name", r.get("name", "?"))
            team = r.get("team", "?")
            pos = r.get("position", "?")
            salary = r.get("salary", 0)
            reason = r.get("reason", "")
            print(f"  {team:12s} | {name:30s} | {pos:15s} | ${salary:>3d}/{ct_code} | {reason}")
        print()

    # Current R-contract players who are NOT eligible
    r_not_eligible = [r for r in not_eligible if r.get("contract_type") == "R"]
    if r_not_eligible:
        print("=" * 100)
        print(f"WARNING: R-CONTRACT PLAYERS WHO EXCEEDED ROOKIE THRESHOLDS: {len(r_not_eligible)}")
        print("=" * 100)
        for r in r_not_eligible:
            name = r.get("mlb_name", r.get("name", "?"))
            team = r.get("team", "?")
            print(f"  {team:12s} | {name:30s} | {r.get('reason', '')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
