"""
Full rookie eligibility audit v2 - saves ALL 500 player results.
No player is omitted from the output.
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
                    results.append({"eligible": False, "error": str(r), "name": "ERROR"})
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
    # SECTION 1: Eligible players
    # ============================================================
    ct_order = {"R": 0, "A": 1, "B": 2, "N": 3, "O": 4, "?": 5}
    eligible.sort(key=lambda x: (
        ct_order.get(x.get("contract_type", ""), 9),
        x.get("team", ""),
        x.get("name", ""),
    ))

    print("=" * 130)
    print(f"  ROOKIE ELIGIBLE: {len(eligible)} / {total}")
    print("=" * 130)
    for ct_label, ct_code in [
        ("R Contract", "R"), ("A Contract", "A"), ("B Contract", "B"),
        ("N Contract", "N"), ("O Contract", "O"), ("? Contract", "?"),
    ]:
        ct_players = [r for r in eligible if r.get("contract_type") == ct_code]
        if not ct_players:
            continue
        print(f"\n  --- {ct_label}: {len(ct_players)} ---")
        for r in ct_players:
            name = r.get("mlb_name", r.get("name", "?"))
            team = r.get("team", "?")
            pos = r.get("position", "?")
            salary = r.get("salary", 0)
            source = r.get("source", "?")
            reason = r.get("reason", "")
            print(f"    {team:12s} | {name:30s} | {pos:12s} | ${salary:>3d}/{ct_code} | src={source:15s} | {reason}")

    # ============================================================
    # SECTION 2: NOT eligible (ALL of them)
    # ============================================================
    not_eligible.sort(key=lambda x: (
        ct_order.get(x.get("contract_type", ""), 9),
        x.get("team", ""),
        x.get("name", ""),
    ))

    print()
    print("=" * 130)
    print(f"  NOT ELIGIBLE: {len(not_eligible)} / {total}")
    print("=" * 130)
    for ct_label, ct_code in [
        ("R Contract (WARNING)", "R"), ("A Contract", "A"), ("B Contract", "B"),
        ("N Contract", "N"), ("O Contract", "O"), ("? Contract", "?"),
    ]:
        ct_players = [r for r in not_eligible if r.get("contract_type") == ct_code]
        if not ct_players:
            continue
        print(f"\n  --- {ct_label}: {len(ct_players)} ---")
        for r in ct_players:
            name = r.get("mlb_name", r.get("name", "?"))
            team = r.get("team", "?")
            pos = r.get("position", "?")
            salary = r.get("salary", 0)
            source = r.get("source", "?")
            reason = r.get("reason", "")
            pa = r.get("career_pa", 0)
            ip = r.get("career_ip", 0)
            print(f"    {team:12s} | {name:30s} | {pos:12s} | ${salary:>3d}/{ct_code} | src={source:15s} | PA={pa:>5d} IP={ip:>7.1f} | {reason}")

    # ============================================================
    # Save ALL results
    # ============================================================
    output = {
        "total_checked": total,
        "eligible_count": len(eligible),
        "not_eligible_count": len(not_eligible),
        "eligible": eligible,
        "not_eligible": not_eligible,
    }
    with open("data/rookie_eligibility_audit_v2.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  ALL {total} results saved to data/rookie_eligibility_audit_v2.json")

    # Quick verification: search for specific players
    print("\n" + "=" * 130)
    print("  SPOT CHECK - key players")
    print("=" * 130)
    spot_check = ["Kumar Rocker", "Travis Bazzana", "Roki Sasaki", "Cade Horton", "Jack Leiter", "Jasson Dominguez", "Roman Anthony"]
    for target in spot_check:
        found_in = None
        for r in results:
            rname = r.get("mlb_name", r.get("name", "")).lower()
            if target.lower() in rname:
                status = "ELIGIBLE" if r.get("eligible") else "NOT ELIGIBLE"
                pa = r.get("career_pa", 0)
                ip = r.get("career_ip", 0)
                ct = r.get("contract_type", "?")
                print(f"    {target:25s} | {ct:3s} | PA={pa:>5d} | IP={ip:>7.1f} | {status}")
                found_in = r
                break
        if not found_in:
            print(f"    {target:25s} | *** NOT FOUND IN RESULTS ***")


if __name__ == "__main__":
    asyncio.run(main())
