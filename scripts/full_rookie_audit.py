"""
Full rookie eligibility audit for ALL 500 players.
Outputs:
1. Players who ARE rookie eligible (grouped by contract type)
2. R-contract players who exceed thresholds (warnings)
3. Non-R-contract players who ARE eligible but not on R contracts
"""
import asyncio
import json
import time

import httpx

MLB_BASE = "https://statsapi.mlb.com/api/v1"
ROOKIE_IP_THRESHOLD = 50
ROOKIE_PA_THRESHOLD = 130
MAX_CONCURRENT = 10


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
    name = player_info["name"]
    position = player_info["position"]

    player = await search_player(client, sem, name, position)
    if not player:
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
                parts.append(f"IP={career_ip:.1f}/50")
            reason = ", ".join(parts)
    else:
        parts = []
        if exceeded_pa:
            parts.append(f"PA={career_pa}>130")
        if exceeded_ip:
            parts.append(f"IP={career_ip:.1f}>50")
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
    with open("data/2026_contracts_v2.json", "r") as f:
        data = json.load(f)

    all_players = []
    for team_id, team_data in data["teams"].items():
        players_list = team_data if isinstance(team_data, list) else team_data.get("players", [])
        for p in players_list:
            if isinstance(p, dict):
                all_players.append({
                    "name": p.get("name", ""),
                    "position": p.get("position", ""),
                    "team": team_id,
                    "contract_type": p.get("contract_type", "?"),
                    "salary": p.get("salary", 0),
                    "source": p.get("source", "unknown"),
                    "mlb_team": p.get("mlb_team", ""),
                })

    total = len(all_players)
    print(f"Checking {total} players against MLB Stats API...")
    print(f"(concurrency: {MAX_CONCURRENT})")
    print()

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    start = time.time()

    async with httpx.AsyncClient(timeout=15.0) as client:
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

    eligible = [r for r in results if r.get("eligible")]
    not_eligible = [r for r in results if not r.get("eligible")]

    # ============================================================
    # SECTION 1: All eligible players grouped by contract type
    # ============================================================
    ct_order = {"R": 0, "A": 1, "B": 2, "N": 3, "O": 4, "?": 5, "FA": 6}
    eligible.sort(key=lambda x: (
        ct_order.get(x.get("contract_type", ""), 9),
        x.get("team", ""),
        x.get("name", ""),
    ))

    print("=" * 120)
    print(f"  ROOKIE ELIGIBLE PLAYERS: {len(eligible)} / {total}")
    print("=" * 120)
    print()

    for ct_label, ct_code in [
        ("R Contract (current rookies)", "R"),
        ("A Contract", "A"),
        ("B Contract", "B"),
        ("N Contract", "N"),
        ("O Contract", "O"),
        ("? Contract (unknown)", "?"),
    ]:
        ct_players = [r for r in eligible if r.get("contract_type") == ct_code]
        if not ct_players:
            continue
        print(f"--- {ct_label}: {len(ct_players)} eligible ---")
        for r in ct_players:
            name = r.get("mlb_name", r.get("name", "?"))
            team = r.get("team", "?")
            pos = r.get("position", "?")
            salary = r.get("salary", 0)
            source = r.get("source", "?")
            reason = r.get("reason", "")
            mlb_team = r.get("mlb_team", "")
            print(
                f"  {team:12s} | {name:30s} | {pos:15s} | ${salary:>3d}/{ct_code} "
                f"| src={source:15s} | MLB={mlb_team:20s} | {reason}"
            )
        print()

    # ============================================================
    # SECTION 2: R-contract players who EXCEED thresholds (WARNINGS)
    # ============================================================
    r_not_eligible = [r for r in not_eligible if r.get("contract_type") == "R"]
    if r_not_eligible:
        print("=" * 120)
        print(f"  WARNING: R-CONTRACT PLAYERS WHO EXCEEDED ROOKIE THRESHOLDS: {len(r_not_eligible)}")
        print("=" * 120)
        for r in r_not_eligible:
            name = r.get("mlb_name", r.get("name", "?"))
            team = r.get("team", "?")
            reason = r.get("reason", "")
            print(f"  {team:12s} | {name:30s} | {reason}")
        print()

    # ============================================================
    # SECTION 3: Summary
    # ============================================================
    print("=" * 120)
    print("  SUMMARY")
    print("=" * 120)
    print(f"  Total players checked: {total}")
    print(f"  Rookie eligible: {len(eligible)}")
    print(f"  Not eligible: {len(not_eligible)}")
    print()

    # Count eligible by source
    from collections import Counter
    eligible_by_source = Counter(r.get("source", "?") for r in eligible)
    print("  Eligible by acquisition source:")
    for src, count in sorted(eligible_by_source.items(), key=lambda x: -x[1]):
        print(f"    {src:20s}: {count}")
    print()

    eligible_by_ct = Counter(r.get("contract_type", "?") for r in eligible)
    print("  Eligible by contract type:")
    for ct, count in sorted(eligible_by_ct.items(), key=lambda x: -x[1]):
        print(f"    {ct:5s}: {count}")

    # Save results to JSON for further analysis
    output = {
        "total_checked": total,
        "eligible_count": len(eligible),
        "not_eligible_count": len(not_eligible),
        "eligible": eligible,
        "r_exceeded": r_not_eligible,
    }
    with open("data/rookie_eligibility_audit.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to data/rookie_eligibility_audit.json")


if __name__ == "__main__":
    asyncio.run(main())
