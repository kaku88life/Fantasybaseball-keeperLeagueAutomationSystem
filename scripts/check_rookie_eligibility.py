"""Check rookie eligibility for all R-contract players via MLB Stats API."""
import asyncio
import httpx

MLB_BASE = "https://statsapi.mlb.com/api/v1"
ROOKIE_IP_THRESHOLD = 50
ROOKIE_PA_THRESHOLD = 130

R_PLAYERS = [
    {"name": "Cade Horton", "position": "SP", "team": "EDDIE"},
    {"name": "Bubba Chandler", "position": "SP", "team": "EDDIE"},
    {"name": "Walker Jenkins", "position": "CF", "team": "Hyper"},
    {"name": "Carson Williams", "position": "SS", "team": "Ponpon"},
    {"name": "Jasson Dominguez", "position": "LF,CF", "team": "Tony"},
    {"name": "Jordan Lawlar", "position": "3B,SS", "team": "rawstuff"},
    {"name": "Roman Anthony", "position": "LF,CF,RF", "team": "rawstuff"},
    {"name": "Rhett Lowder", "position": "SP", "team": "xiaozhe"},
    {"name": "Jack Leiter", "position": "SP", "team": "Kaku"},
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
        return {"name": name, "found": False}

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

    resp2 = await client.get(
        f"{MLB_BASE}/people/{mlb_id}/stats",
        params={"stats": "career", "group": "hitting,pitching"},
    )
    stats_data = resp2.json()

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

    return {
        "name": name,
        "mlb_name": mlb_name,
        "found": True,
        "career_pa": career_pa,
        "career_ip": round(career_ip, 1),
        "exceeded_pa": exceeded_pa,
        "exceeded_ip": exceeded_ip,
        "eligible": eligible,
    }


async def main():
    async with httpx.AsyncClient(timeout=15.0) as client:
        results = []
        for p in R_PLAYERS:
            try:
                result = await check_player(client, p["name"], p["position"])
                result["team"] = p["team"]
                result["position"] = p["position"]
                results.append(result)
                print(f"  Checked: {p['name']}")
            except Exception as e:
                print(f"  ERROR checking {p['name']}: {e}")
                results.append(
                    {"name": p["name"], "team": p["team"], "found": False, "error": str(e)}
                )

    print()
    print("=" * 90)
    print("R CONTRACT PLAYERS - ROOKIE ELIGIBILITY CHECK")
    print("=" * 90)
    print()

    eligible_list = []
    not_eligible_list = []

    for r in results:
        if not r.get("found", False):
            print(
                f"  {r['team']:12s} | {r['name']:25s} | NOT FOUND (no MLB record = ELIGIBLE)"
            )
            eligible_list.append(r)
            continue

        status = "ELIGIBLE" if r["eligible"] else "NOT ELIGIBLE"
        pa_flag = " *EXCEEDED*" if r.get("exceeded_pa") else ""
        ip_flag = " *EXCEEDED*" if r.get("exceeded_ip") else ""

        print(
            f"  {r['team']:12s} | {r['name']:25s} | "
            f"PA: {r['career_pa']:>4d}/130{pa_flag:12s} | "
            f"IP: {r['career_ip']:>6.1f}/50{ip_flag:12s} | "
            f"{status}"
        )

        if r["eligible"]:
            eligible_list.append(r)
        else:
            not_eligible_list.append(r)

    print()
    print(f"Eligible: {len(eligible_list)}, Not Eligible: {len(not_eligible_list)}")

    if not_eligible_list:
        print()
        print("WARNING: The following R-contract players have EXCEEDED rookie thresholds:")
        for r in not_eligible_list:
            print(
                f"  - {r['name']} ({r['team']}): "
                f"PA={r.get('career_pa', 0)}, IP={r.get('career_ip', 0)}"
            )


if __name__ == "__main__":
    asyncio.run(main())
