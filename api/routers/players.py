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
    """Fetch year-by-year stats for a player from MLB Stats API."""
    cache_key = f"stats:{mlb_id}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{MLB_BASE}/people/{mlb_id}/stats",
            params={
                "stats": "yearByYear",
                "group": "hitting,pitching",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _set_cached(cache_key, data)
    return data


# ========== Endpoint ==========


@router.get("/stats")
async def get_player_stats(
    name: str = Query(..., description="Player name"),
    position: str = Query("", description="Player position code (e.g. SP, C, LF)"),
):
    """Look up a player's MLB year-by-year stats via MLB Stats API."""
    player = await _search_mlb_player(name, position)
    if not player:
        raise HTTPException(
            status_code=404,
            detail=f"Player '{name}' not found on MLB.com",
        )

    mlb_id = player["id"]
    raw_stats = await _get_mlb_stats(mlb_id)

    # Parse into hitting + pitching season lists
    hitting_seasons = []
    pitching_seasons = []

    for stat_group in raw_stats.get("stats", []):
        group_name = stat_group.get("group", {}).get("displayName", "")
        for split in stat_group.get("splits", []):
            season = split.get("season", "")
            team_name = split.get("team", {}).get("name", "")
            s = split.get("stat", {})

            # Only include MLB-level stats (sport.id == 1)
            sport_id = split.get("sport", {}).get("id")
            if sport_id != 1:
                continue

            if group_name == "hitting":
                hitting_seasons.append({
                    "season": season,
                    "team": team_name,
                    "games": s.get("gamesPlayed", 0),
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
    }
