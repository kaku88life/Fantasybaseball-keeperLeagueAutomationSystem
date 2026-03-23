"""
Rookie call-up monitoring.
Detects when minor league players get called up to MLB and sends
LINE group notifications. Only notifies once per player per season.

Detection: MLB Stats API (mlbDebutDate + current season game log).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx

MLB_BASE = "https://statsapi.mlb.com/api/v1"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Cache searched MLB IDs within a single run to avoid repeated lookups
_mlb_id_cache: dict[str, int | None] = {}


def _load_r_contract_players(year: int) -> list[dict]:
    """Load R-contract players from the contracts JSON file.

    Returns list of dicts with: name, player_key, position, mlb_team,
    owner_manager, owner_team_id.
    """
    # Try to load from DB first (player has R contract for this year)
    try:
        from api.database import get_db
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT ks.player_name, t.manager_name, t.id as team_id
                       FROM keeper_selections ks
                       JOIN teams t ON ks.team_id = t.id
                       WHERE ks.year = %s AND ks.action = 'keep'
                       AND ks.player_name IN (
                           SELECT player_name FROM keeper_selections
                           WHERE year = %s
                       )""",
                    (year, year),
                )
                # This is a fallback; primary source is the JSON
        finally:
            conn.close()
    except Exception:
        pass

    # Primary: load from contracts JSON (nested structure: teams -> manager -> players)
    contracts_path = DATA_DIR / f"{year}_contracts_v2.json"
    if not contracts_path.exists():
        print(f"[RookieMonitor] Contracts file not found: {contracts_path}")
        return []

    with open(contracts_path, encoding="utf-8") as f:
        contracts = json.load(f)

    r_players = []
    teams_data = contracts.get("teams", {})
    for manager_name, team_data in teams_data.items():
        for player in team_data.get("players", []):
            ct = player.get("contract_2026_type", player.get("contract_type", ""))
            if ct == "R":
                r_players.append({
                    "name": player["name"],
                    "player_key": player.get("player_key", ""),
                    "position": player.get("position", ""),
                    "mlb_team": player.get("mlb_team", ""),
                    "owner_manager": manager_name,
                    "owner_team_id": 0,
                })

    return r_players


def _search_mlb_id(name: str) -> int | None:
    """Search MLB Stats API for a player's MLB ID (synchronous)."""
    if name in _mlb_id_cache:
        return _mlb_id_cache[name]

    clean_name = name.split("(")[0].strip()
    try:
        resp = httpx.get(
            f"{MLB_BASE}/people/search",
            params={"names": clean_name, "hydrate": "currentTeam"},
            timeout=10.0,
        )
        resp.raise_for_status()
        people = resp.json().get("people", [])
        if people:
            mlb_id = people[0]["id"]
            _mlb_id_cache[name] = mlb_id
            return mlb_id
    except Exception as e:
        print(f"[RookieMonitor] MLB search failed for {name}: {e}")

    _mlb_id_cache[name] = None
    return None


def _check_mlb_debut(mlb_id: int, season: int) -> dict | None:
    """Check if a player has debuted in MLB or has game activity this season.

    Returns dict with debut info if called up, None otherwise.
    """
    try:
        resp = httpx.get(
            f"{MLB_BASE}/people/{mlb_id}",
            params={"hydrate": "currentTeam,stats(type=gameLog,season={},group=hitting,pitching,sportId=1)".format(season)},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        people = data.get("people", [])
        if not people:
            return None

        person = people[0]
        debut_date = person.get("mlbDebutDate", "")
        current_team = person.get("currentTeam", {})
        active = person.get("active", False)

        # Check if player has any MLB stats this season
        has_season_stats = False
        stats = person.get("stats", [])
        for stat_group in stats:
            splits = stat_group.get("splits", [])
            for split in splits:
                if split.get("season") == str(season):
                    has_season_stats = True
                    break
            if has_season_stats:
                break

        # A call-up is detected if:
        # 1. Player debuted this season (mlbDebutDate in current year), or
        # 2. Player is currently on an MLB roster (active with currentTeam), or
        # 3. Player has MLB game stats this season
        is_debut_this_year = debut_date and debut_date.startswith(str(season))
        is_on_mlb_roster = active and current_team.get("sport", {}).get("id") == 1

        if is_debut_this_year or is_on_mlb_roster or has_season_stats:
            return {
                "mlb_id": mlb_id,
                "full_name": person.get("fullName", ""),
                "debut_date": debut_date,
                "current_team": current_team.get("name", ""),
                "current_team_abbr": current_team.get("abbreviation", ""),
                "active": active,
                "is_debut_this_year": is_debut_this_year,
                "has_season_stats": has_season_stats,
            }

    except Exception as e:
        print(f"[RookieMonitor] MLB debut check failed for ID {mlb_id}: {e}")

    return None


def check_rookie_callups(year: int) -> list[dict]:
    """Check all R-contract players for new MLB call-ups.

    Returns list of newly detected call-ups (not previously notified).
    Each item: {name, position, mlb_team, owner_manager, debut_info, ...}
    """
    from api.database import get_notified_callups

    # Get already-notified players for this season
    already_notified = get_notified_callups(year)
    print(f"[RookieMonitor] Already notified this season: {len(already_notified)} players")

    # Load R-contract players
    r_players = _load_r_contract_players(year)
    if not r_players:
        print("[RookieMonitor] No R-contract players found to monitor.")
        return []
    print(f"[RookieMonitor] Monitoring {len(r_players)} R-contract players...")

    new_callups = []

    for player in r_players:
        name = player["name"]

        # Skip if already notified
        if name in already_notified:
            continue

        # Search for MLB ID
        mlb_id = _search_mlb_id(name)
        if not mlb_id:
            continue

        # Check for MLB debut/activity
        debut_info = _check_mlb_debut(mlb_id, year)
        if debut_info:
            new_callups.append({
                **player,
                "debut_info": debut_info,
            })
            print(f"[RookieMonitor] NEW CALL-UP: {name} "
                  f"({player['position']}, {debut_info.get('current_team_abbr', '?')})")

    return new_callups


def send_callup_notifications(year: int) -> dict:
    """Main entry: detect call-ups and send LINE notifications.

    Returns summary dict with counts and details.
    """
    from api.database import record_callup
    from src.notification.line_service import send_line_group_message

    new_callups = check_rookie_callups(year)

    if not new_callups:
        return {
            "checked": True,
            "new_callups": 0,
            "notified": False,
            "players": [],
        }

    # Build LINE message
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
    lines = [
        f"[5-Man Keeper League] 新秀上大聯盟通知",
        f"Rookie Call-up Alert",
        "",
    ]
    for cu in new_callups:
        di = cu["debut_info"]
        debut_str = f" (debut: {di['debut_date']})" if di.get("is_debut_this_year") else ""
        lines.append(
            f"  {cu['name']} ({cu['position']}) - {cu['owner_manager']} 隊"
        )
        lines.append(
            f"  -> {di.get('current_team', cu['mlb_team'])}{debut_str}"
        )
        lines.append("")

    lines.append(f"球員資料庫 Players DB:")
    lines.append(f"{frontend_url}/players")

    message = "\n".join(lines)

    # Record in DB + send notification
    notified_names = []
    for cu in new_callups:
        di = cu["debut_info"]
        record_callup(
            player_name=cu["name"],
            year=year,
            player_key=cu.get("player_key", ""),
            mlb_team=di.get("current_team_abbr", cu.get("mlb_team", "")),
            owner_manager=cu.get("owner_manager", ""),
            owner_team_id=cu.get("owner_team_id", 0),
            callup_date=di.get("debut_date") or None,
            detection_source="mlb_api",
        )
        notified_names.append(cu["name"])

    # Send LINE message
    success, error = send_line_group_message(message)
    if success:
        print(f"[RookieMonitor] LINE notification sent for {len(new_callups)} call-ups")
    else:
        print(f"[RookieMonitor] LINE send failed: {error}")

    return {
        "checked": True,
        "new_callups": len(new_callups),
        "notified": success,
        "error": error if not success else None,
        "players": notified_names,
    }
