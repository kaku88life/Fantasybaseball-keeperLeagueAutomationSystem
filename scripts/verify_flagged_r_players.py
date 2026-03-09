"""Verify year-by-year MLB stats for flagged R-contract players."""
import asyncio
import httpx

MLB_BASE = "https://statsapi.mlb.com/api/v1"

PLAYERS = [
    {"name": "Cade Horton", "position": "SP"},
    {"name": "Jack Leiter", "position": "SP"},
    {"name": "Jasson Dominguez", "position": "LF,CF"},
    {"name": "Roman Anthony", "position": "LF,CF,RF"},
]


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


async def check_player(client, name, position):
    clean_name = name.split("(")[0].strip()
    resp = await client.get(
        f"{MLB_BASE}/people/search",
        params={"names": clean_name, "hydrate": "currentTeam"},
    )
    data = resp.json()
    rows = data.get("people", [])
    if not rows:
        print(f"\n{'='*60}")
        print(f"  {name}: NOT FOUND in MLB API")
        return

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

    mlb_id = best["id"]
    mlb_name = best.get("fullName", name)
    pos = best.get("primaryPosition", {}).get("abbreviation", "?")

    # Get year-by-year + career stats
    resp2 = await client.get(
        f"{MLB_BASE}/people/{mlb_id}/stats",
        params={"stats": "yearByYear,career", "group": "hitting,pitching"},
    )
    stats_data = resp2.json()

    print(f"\n{'='*60}")
    print(f"  {mlb_name} (ID: {mlb_id}, Position: {pos})")
    print(f"{'='*60}")

    career_pa = 0
    career_ip = 0.0

    for stat_group in stats_data.get("stats", []):
        group_name = stat_group.get("group", {}).get("displayName", "")
        stat_type = stat_group.get("type", {}).get("displayName", "")

        for split in stat_group.get("splits", []):
            sport_id = split.get("sport", {}).get("id")
            # Only MLB level
            if sport_id is not None and sport_id != 1:
                continue

            s = split.get("stat", {})
            season = split.get("season", "career")
            team_name = split.get("team", {}).get("name", "N/A")

            if stat_type == "career":
                if group_name == "hitting":
                    career_pa = s.get("plateAppearances", 0)
                    print(f"  [CAREER HITTING] PA={career_pa}, G={s.get('gamesPlayed', 0)}, AB={s.get('atBats', 0)}, H={s.get('hits', 0)}, HR={s.get('homeRuns', 0)}, AVG={s.get('avg', '.000')}")
                elif group_name == "pitching":
                    career_ip = parse_ip(s.get("inningsPitched", "0.0"))
                    print(f"  [CAREER PITCHING] IP={s.get('inningsPitched', '0.0')} ({career_ip:.1f}), G={s.get('gamesPlayed', 0)}, GS={s.get('gamesStarted', 0)}, W={s.get('wins', 0)}, L={s.get('losses', 0)}, ERA={s.get('era', '0.00')}, K={s.get('strikeOuts', 0)}")

            elif stat_type == "yearByYear":
                if group_name == "hitting":
                    pa = s.get("plateAppearances", 0)
                    print(f"  {season} {team_name:30s} | HITTING  | G={s.get('gamesPlayed', 0):>3d}, PA={pa:>4d}, AB={s.get('atBats', 0):>4d}, H={s.get('hits', 0):>3d}, HR={s.get('homeRuns', 0):>2d}, AVG={s.get('avg', '.000')}")
                elif group_name == "pitching":
                    ip_str = s.get("inningsPitched", "0.0")
                    ip_val = parse_ip(ip_str)
                    print(f"  {season} {team_name:30s} | PITCHING | G={s.get('gamesPlayed', 0):>3d}, GS={s.get('gamesStarted', 0):>3d}, IP={ip_str:>6s} ({ip_val:.1f}), W={s.get('wins', 0)}, L={s.get('losses', 0)}, ERA={s.get('era', '0.00')}, K={s.get('strikeOuts', 0)}")

    print()
    exceeded_pa = career_pa > 130
    exceeded_ip = career_ip > 50
    eligible = not exceeded_pa and not exceeded_ip

    status = "ELIGIBLE" if eligible else "NOT ELIGIBLE"
    reasons = []
    if exceeded_pa:
        reasons.append(f"PA={career_pa}>130")
    if exceeded_ip:
        reasons.append(f"IP={career_ip:.1f}>50")
    if not reasons:
        if career_pa == 0 and career_ip == 0:
            reasons.append("no MLB stats")
        else:
            if career_pa > 0:
                reasons.append(f"PA={career_pa}/130")
            if career_ip > 0:
                reasons.append(f"IP={career_ip:.1f}/50")

    print(f"  >>> ROOKIE STATUS: {status} ({', '.join(reasons)})")


async def main():
    async with httpx.AsyncClient(timeout=15.0) as client:
        for p in PLAYERS:
            await check_player(client, p["name"], p["position"])


if __name__ == "__main__":
    asyncio.run(main())
