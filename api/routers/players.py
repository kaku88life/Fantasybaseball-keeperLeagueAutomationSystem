"""
Fantasy Baseball Keeper League - Player Stats Routes
Uses MLB Stats API (statsapi.mlb.com) for player statistics.
No authentication required - MLB stats are public data.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from config.settings import ROOKIE_IP_THRESHOLD, ROOKIE_PA_THRESHOLD
from api.database import (
    get_all_submissions,
    get_all_teams,
    get_player_rankings,
    get_ranking_fetch_status,
    get_snapshot,
)
from api.serializers import dict_to_league_state

router = APIRouter()

# ========== In-memory cache ==========
# key: "search:{name}:{position}" or "stats:{mlb_id}"
# value: (data, timestamp)
_cache: dict[str, tuple[dict | list, float]] = {}
CACHE_TTL = 86400  # 24 hours


def _get_cached(key: str) -> Optional[dict | list]:
    """Return cached data if still valid, else None."""
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _set_cached(key: str, data: dict | list) -> None:
    """Store data in cache with current timestamp."""
    _cache[key] = (data, time.time())


MLB_BASE = "https://statsapi.mlb.com/api/v1"


def _parse_ip(ip_str: str) -> float:
    """Parse innings pitched string like '50.1' into a float.

    MLB uses fractional notation: 50.1 = 50 1/3 IP, 50.2 = 50 2/3 IP.
    """
    try:
        parts = str(ip_str).split(".")
        whole = int(parts[0])
        if len(parts) > 1:
            thirds = int(parts[1])
            return whole + thirds / 3.0
        return float(whole)
    except (ValueError, IndexError):
        return 0.0


# ========== MLB API helpers ==========


async def _search_mlb_player(name: str, position: str = "") -> Optional[dict]:
    """Search for a player by name on MLB Stats API.

    Returns the best match dict with keys: id, fullName, primaryPosition, etc.
    """
    # Clean up name: remove suffixes like "(Batter)", "(Pitcher)"
    clean_name = name.split("(")[0].strip()

    cache_key = f"search:{clean_name}:{position}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{MLB_BASE}/people/search",
            params={"names": clean_name, "hydrate": "currentTeam"},
        )
        resp.raise_for_status()
        data = resp.json()

    rows = data.get("people", [])
    if not rows:
        return None

    # Try position-based matching if multiple results
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

    _set_cached(cache_key, best)
    return best


async def _get_mlb_stats(mlb_id: int) -> dict:
    """Fetch year-by-year AND career stats for a player from MLB Stats API.

    Uses stats=yearByYear,career to get both in a single API call.
    """
    cache_key = f"stats:{mlb_id}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{MLB_BASE}/people/{mlb_id}/stats",
            params={
                "stats": "yearByYear,career",
                "group": "hitting,pitching",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _set_cached(cache_key, data)
    return data


# ========== Endpoint ==========


@router.get("/database/{year}")
async def get_player_database(year: int):
    """Get the full player database for a year.

    Combines league snapshot data (ownership, contracts) with
    player rankings (O_Rank, X_Rank, stats, projections).
    No authentication required - public endpoint.
    """
    # 1. Load league snapshot for ownership data
    snapshot = get_snapshot(year)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No league data for year {year}")

    league_state = dict_to_league_state(snapshot["data"])

    # 1b. Load submission data for next-year contract status
    submissions = get_all_submissions(year)
    submitted_managers: set[str] = set()
    selection_lookup: dict[str, dict] = {}  # "manager::player_name" -> selection
    for sub in submissions:
        mgr = sub.get("manager_name", "")
        submitted_managers.add(mgr)
        for sel in sub.get("selections", []):
            selection_lookup[f"{mgr}::{sel['player_name']}"] = sel

    # 2. Build player -> owner mapping from league snapshot
    # Flatten all players across all teams
    owner_map: dict[str, dict] = {}  # player_key -> owner info
    player_name_map: dict[str, dict] = {}  # player_name -> owner info (fallback)

    all_league_players: list[dict] = []

    for team in league_state.teams:
        for p in team.players:
            player_entry = {
                "name": p.name,
                "position": p.position,
                "mlb_team": p.mlb_team,
                "contract_type": p.contract.contract_type.value,
                "salary": p.contract.salary,
                "extension_years": p.contract.extension_years,
                "contract_display": p.contract.display,
                "is_keepable": p.contract.is_keepable,
                "owner_manager": team.manager_name,
                "yahoo_player_id": p.yahoo_player_id or "",
                # Rankings (filled later if available)
                "o_rank": None,
                "ar_rank": None,
                "stats": {},
                "projections": {},
                # Next year contract status
                "next_contract_display": "",
                "next_contract_type": "",
            }

            # Compute next-year (2026) contract status
            nc_display, nc_type = _compute_next_year_status(
                player_entry, submitted_managers, selection_lookup,
            )
            player_entry["next_contract_display"] = nc_display
            player_entry["next_contract_type"] = nc_type

            all_league_players.append(player_entry)

            # Index by player_key for matching with rankings
            if p.yahoo_player_id:
                owner_map[p.yahoo_player_id] = player_entry
            player_name_map[p.name.lower()] = player_entry

    # 3. Load rankings if available
    rankings = get_player_rankings(year)
    ranking_status = get_ranking_fetch_status(year)

    # Build ranked player list (may include unowned players)
    ranked_players: list[dict] = []
    matched_keys = set()

    for r in rankings:
        player_key = r["player_key"]

        # Try to match with league player by player_key
        league_player = owner_map.get(player_key)
        if not league_player:
            # Fallback: match by name
            league_player = player_name_map.get(r["player_name"].lower())

        if league_player:
            # Merge ranking data into league player
            league_player["o_rank"] = r.get("o_rank")
            league_player["ar_rank"] = r.get("ar_rank")

            # Override position/mlb_team from ranking if league data is empty
            if not league_player["position"] and r.get("position"):
                league_player["position"] = r["position"]
            if not league_player["mlb_team"] and r.get("mlb_team"):
                league_player["mlb_team"] = r["mlb_team"]

            # Stats
            league_player["stats"] = _extract_stats(r, "stat")
            league_player["projections"] = _extract_stats(r, "proj")

            matched_keys.add(player_key)
        else:
            # Unowned player from rankings
            ranked_players.append({
                "name": r["player_name"],
                "position": r.get("position", ""),
                "mlb_team": r.get("mlb_team", ""),
                "contract_type": "",
                "salary": 0,
                "extension_years": 0,
                "contract_display": "",
                "is_keepable": False,
                "owner_manager": "",
                "yahoo_player_id": player_key,
                "o_rank": r.get("o_rank"),
                "ar_rank": r.get("ar_rank"),
                "stats": _extract_stats(r, "stat"),
                "projections": _extract_stats(r, "proj"),
                "next_contract_display": "",
                "next_contract_type": "",
            })

    # 4. Combine: league players + unowned ranked players
    combined = all_league_players + ranked_players

    # Sort: ranked players first (by o_rank), then unranked
    combined.sort(key=lambda p: (p["o_rank"] if p["o_rank"] is not None else 99999))

    return {
        "year": year,
        "total_count": len(combined),
        "has_rankings": ranking_status["has_data"],
        "last_fetched_at": ranking_status.get("last_fetched_at"),
        "players": combined,
    }


def _compute_next_year_status(
    player_entry: dict,
    submitted_managers: set[str],
    selection_lookup: dict[str, dict],
) -> tuple[str, str]:
    """Compute next-year contract status for a player.

    Returns (next_contract_display, next_contract_type).
    Logic:
    - Unowned players -> ("", "")
    - Submitted team + has selection -> use next_contract from submission
    - Submitted team + no selection -> auto-released -> ("FA", "FA")
    - Unsubmitted + O contract -> deterministic FA
    - Unsubmitted + N(x) -> deterministic mandatory evolution
    - Unsubmitted + A/B/R -> pending ("待定", "TBD")
    """
    owner = player_entry["owner_manager"]
    if not owner:
        return ("", "")

    name = player_entry["name"]
    contract_type = player_entry["contract_type"]

    # Team has submitted keeper selections
    if owner in submitted_managers:
        key = f"{owner}::{name}"
        sel = selection_lookup.get(key)
        if sel:
            nc = sel.get("next_contract", "")
            if not nc or nc == "FA":
                return ("FA", "FA")
            nc_type = _parse_contract_type_from_display(nc)
            return (nc, nc_type)
        # Player not in selections -> auto-released
        return ("FA", "FA")

    # Team has NOT submitted — compute based on contract rules
    if contract_type == "O":
        return ("FA", "FA")

    if contract_type == "N":
        ext = player_entry["extension_years"]
        salary = player_entry["salary"]
        if ext > 1:
            return (f"${salary}/N{ext - 1}", "N")
        else:
            return (f"${salary}/O", "O")

    # A, B, R contracts are not deterministic without keeper selection
    if contract_type in ("A", "B", "R"):
        return ("\u5f85\u5b9a", "TBD")

    # FA or unknown
    return ("", "")


def _parse_contract_type_from_display(display: str) -> str:
    """Parse contract type letter from display string.

    Examples: '$20/B' -> 'B', '$35/N3' -> 'N', '$5/R' -> 'R', '$20/A' -> 'A'
    """
    if "/" not in display:
        return ""
    part = display.split("/")[-1]
    if part.startswith("N"):
        return "N"
    return part


def _extract_stats(row: dict, prefix: str) -> dict:
    """Extract stat/proj fields from a player_rankings row into a clean dict."""
    result = {}
    stat_keys = ["r", "h", "hr", "rbi", "sb", "avg", "ops",
                 "w", "sv", "hld", "k", "era", "whip", "qs"]
    for key in stat_keys:
        val = row.get(f"{prefix}_{key}")
        if val is not None:
            result[key] = val
    return result


@router.get("/stats")
async def get_player_stats(
    name: str = Query(..., description="Player name"),
    position: str = Query("", description="Player position code (e.g. SP, C, LF)"),
):
    """Look up a player's MLB year-by-year stats via MLB Stats API.

    Also returns career totals and rookie eligibility status.
    """
    player = await _search_mlb_player(name, position)
    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player '{name}' not found on MLB.com",
        )

    mlb_id = player["id"]
    raw_stats = await _get_mlb_stats(mlb_id)

    # Parse into hitting + pitching season lists AND career totals
    hitting_seasons = []
    pitching_seasons = []
    career_pa = 0
    career_ip = 0.0

    for stat_group in raw_stats.get("stats", []):
        group_name = stat_group.get("group", {}).get("displayName", "")
        stat_type = stat_group.get("type", {}).get("displayName", "")

        for split in stat_group.get("splits", []):
            s = split.get("stat", {})

            # Only include MLB-level stats (sport.id == 1)
            sport_id = split.get("sport", {}).get("id")
            if sport_id is not None and sport_id != 1:
                continue

            # Career totals (stat_type == "career")
            if stat_type == "career":
                if group_name == "hitting":
                    career_pa = s.get("plateAppearances", 0)
                elif group_name == "pitching":
                    career_ip = _parse_ip(s.get("inningsPitched", "0.0"))
                continue

            # Year-by-year stats
            if stat_type != "yearByYear":
                continue

            season = split.get("season", "")
            team_name = split.get("team", {}).get("name", "")

            if group_name == "hitting":
                hitting_seasons.append({
                    "season": season,
                    "team": team_name,
                    "games": s.get("gamesPlayed", 0),
                    "plate_appearances": s.get("plateAppearances", 0),
                    "at_bats": s.get("atBats", 0),
                    "hits": s.get("hits", 0),
                    "home_runs": s.get("homeRuns", 0),
                    "rbi": s.get("rbi", 0),
                    "runs": s.get("runs", 0),
                    "stolen_bases": s.get("stolenBases", 0),
                    "avg": s.get("avg", ".000"),
                    "obp": s.get("obp", ".000"),
                    "slg": s.get("slg", ".000"),
                    "ops": s.get("ops", ".000"),
                })
            elif group_name == "pitching":
                pitching_seasons.append({
                    "season": season,
                    "team": team_name,
                    "games": s.get("gamesPlayed", 0),
                    "games_started": s.get("gamesStarted", 0),
                    "wins": s.get("wins", 0),
                    "losses": s.get("losses", 0),
                    "era": s.get("era", "0.00"),
                    "innings_pitched": s.get("inningsPitched", "0.0"),
                    "strikeouts": s.get("strikeOuts", 0),
                    "walks": s.get("baseOnBalls", 0),
                    "whip": s.get("whip", "0.00"),
                    "saves": s.get("saves", 0),
                    "holds": s.get("holds", 0),
                })

    # Sort by season descending, take last 5 years
    hitting_seasons.sort(key=lambda x: x["season"], reverse=True)
    pitching_seasons.sort(key=lambda x: x["season"], reverse=True)

    # Determine rookie eligibility
    exceeded_pa = career_pa > ROOKIE_PA_THRESHOLD
    exceeded_ip = career_ip > ROOKIE_IP_THRESHOLD
    rookie_eligible = not exceeded_pa and not exceeded_ip

    return {
        "mlb_id": mlb_id,
        "name": player.get("fullName", name),
        "primary_position": player.get("primaryPosition", {}).get("abbreviation", ""),
        "current_team": player.get("currentTeam", {}).get("name", ""),
        "birth_date": player.get("birthDate", ""),
        "age": player.get("currentAge"),
        "bat_side": player.get("batSide", {}).get("code", ""),
        "pitch_hand": player.get("pitchHand", {}).get("code", ""),
        "hitting": hitting_seasons[:5],
        "pitching": pitching_seasons[:5],
        # Career totals and rookie eligibility
        "career_pa": career_pa,
        "career_ip": round(career_ip, 1),
        "rookie_eligible": rookie_eligible,
        "rookie_thresholds": {
            "pa_threshold": ROOKIE_PA_THRESHOLD,
            "ip_threshold": ROOKIE_IP_THRESHOLD,
            "exceeded_pa": exceeded_pa,
            "exceeded_ip": exceeded_ip,
        },
    }
