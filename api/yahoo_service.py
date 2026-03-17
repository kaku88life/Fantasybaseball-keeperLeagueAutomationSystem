"""
Yahoo Fantasy API service - DB-backed token management.

For use by backend services and background jobs that need Yahoo API access
without relying on filesystem (oauth2.json).

Falls back to oauth2.json if no DB tokens exist (local dev compatibility).
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

# Buffer before expiry to trigger proactive refresh (5 minutes)
_REFRESH_BUFFER_SECONDS = 300


class YahooTokenError(Exception):
    """Raised when Yahoo token is missing or refresh fails."""
    pass


def _get_client_credentials() -> tuple[str, str]:
    """Get Yahoo OAuth client ID and secret from env vars."""
    client_id = os.getenv("YAHOO_CLIENT_ID", "")
    client_secret = os.getenv("YAHOO_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise YahooTokenError(
            "YAHOO_CLIENT_ID / YAHOO_CLIENT_SECRET env vars not set"
        )
    return client_id, client_secret


def _try_oauth2_json_fallback() -> Optional[str]:
    """Try to load access token from oauth2.json (local dev fallback)."""
    oauth_file = Path(__file__).resolve().parent.parent / "oauth2.json"
    if not oauth_file.exists():
        return None
    try:
        creds = json.loads(oauth_file.read_text())
        token = creds.get("access_token", "")
        if token:
            print("[YahooService] Using oauth2.json fallback (local dev)", flush=True)
            return token
    except Exception:
        pass
    return None


def get_valid_access_token() -> str:
    """
    Get a valid Yahoo access token.

    Priority:
    1. DB-backed commissioner token (auto-refresh if expired)
    2. oauth2.json fallback (local dev)

    Returns: valid access_token string
    Raises: YahooTokenError if no token available
    """
    from api.database import get_commissioner_yahoo_token

    token_row = get_commissioner_yahoo_token()

    if token_row:
        # Check if token is still valid (with buffer)
        expires_at = token_row.get("expires_at")
        now = datetime.datetime.now(datetime.timezone.utc)

        if expires_at:
            # Handle timezone-naive datetimes from DB
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            if now >= expires_at - datetime.timedelta(seconds=_REFRESH_BUFFER_SECONDS):
                # Token expired or about to expire, refresh it
                return refresh_db_token(token_row)

        return token_row["access_token"]

    # Fallback to oauth2.json for local dev
    fallback_token = _try_oauth2_json_fallback()
    if fallback_token:
        return fallback_token

    raise YahooTokenError(
        "No Yahoo token available. Commissioner must log in via Yahoo OAuth."
    )


def refresh_db_token(token_row: dict) -> str:
    """
    Refresh an expired token using the refresh_token from DB.
    Updates DB with new access_token and rotated refresh_token.

    Returns: new access_token
    Raises: YahooTokenError if refresh fails
    """
    from api.database import upsert_yahoo_token

    refresh_token = token_row.get("refresh_token", "")
    if not refresh_token:
        raise YahooTokenError("No refresh_token available. Commissioner must re-login.")

    client_id, client_secret = _get_client_credentials()

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=HTTPBasicAuth(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise YahooTokenError(f"Token refresh request failed: {e}")

    if resp.status_code != 200:
        raise YahooTokenError(
            f"Token refresh failed ({resp.status_code}): {resp.text[:300]}"
        )

    data = resp.json()
    new_access_token = data["access_token"]
    new_refresh_token = data.get("refresh_token", refresh_token)
    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=expires_in
    )

    # Update DB
    upsert_yahoo_token(
        user_id=token_row["user_id"],
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=expires_at,
        yahoo_guid=token_row.get("yahoo_guid", ""),
    )

    print(
        f"[YahooService] Token refreshed for user #{token_row['user_id']}, "
        f"expires at {expires_at.isoformat()}",
        flush=True,
    )
    return new_access_token


def yahoo_api_get(path: str) -> dict:
    """
    Perform a GET request to Yahoo Fantasy API with auto-refresh.
    Retries once on 401.

    Args:
        path: API path (e.g., "/league/469.l.80910/standings")

    Returns:
        Parsed JSON response

    Raises:
        YahooTokenError: if no valid token
        RuntimeError: if API call fails after retry
    """
    url = f"{BASE_URL}{path}"
    separator = "&" if "?" in url else "?"
    url += f"{separator}format=json"

    access_token = get_valid_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers, timeout=15)

    # Retry once on 401 (token may have expired between check and request)
    if resp.status_code == 401:
        print("[YahooService] Got 401, forcing token refresh and retry", flush=True)
        from api.database import get_commissioner_yahoo_token
        token_row = get_commissioner_yahoo_token()
        if token_row:
            access_token = refresh_db_token(token_row)
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Yahoo API request failed ({resp.status_code}): {resp.text[:300]}"
        )

    return resp.json()


def discover_league_keys() -> dict[int, str]:
    """Discover all 5-Man Keep league keys across years using DB-backed token."""
    import re

    data = yahoo_api_get("/users;use_login=1/games;game_codes=mlb/leagues")
    raw = json.dumps(data, ensure_ascii=False)

    gk_to_season = {
        "346": 2013, "357": 2014, "370": 2015, "378": 2016,
        "388": 2017, "398": 2018, "404": 2019, "412": 2020,
        "422": 2023, "431": 2024, "458": 2025, "469": 2026,
    }

    league_keys: dict[int, str] = {}
    for gk, season in gk_to_season.items():
        pattern = rf"{gk}\.l\.(\d+)"
        for match in re.finditer(pattern, raw):
            league_key = f"{gk}.l.{match.group(1)}"
            idx = raw.find(league_key)
            nearby = raw[idx : idx + 400]
            if "5-Man" in nearby or "Keeper" in nearby:
                league_keys[season] = league_key

    return league_keys


def fetch_draft_results(league_key: str) -> list[dict]:
    """Fetch draft results with auction prices for a given league key."""
    data = yahoo_api_get(f"/league/{league_key}/draftresults")
    dr_data = data["fantasy_content"]["league"][1]["draft_results"]
    count = dr_data.get("count", 0)

    # Also fetch team info to map team_key -> manager
    teams_data = yahoo_api_get(f"/league/{league_key}/teams")
    teams_raw = teams_data["fantasy_content"]["league"][1]["teams"]
    team_count = teams_raw.get("count", 0)
    key_to_mgr = {}
    for i in range(team_count):
        team_raw = teams_raw[str(i)]["team"]
        team_info = _parse_yahoo_team(team_raw)
        key_to_mgr[team_info["team_key"]] = team_info["manager"]

    results = []
    for i in range(count):
        pick = dr_data[str(i)]["draft_result"]
        tk = pick.get("team_key", "")
        pk = pick.get("player_key", "")

        results.append({
            "round": int(pick.get("round", 0)),
            "pick": int(pick.get("pick", 0)),
            "team_key": tk,
            "player_key": pk,
            "cost": int(pick.get("cost", 0)),
            "player_name": "",  # will be resolved below
            "manager": key_to_mgr.get(tk, ""),
        })

    # Batch-resolve player names and positions
    player_keys = list({r["player_key"] for r in results if r["player_key"]})
    player_info = _batch_resolve_players(league_key, player_keys)
    for r in results:
        info = player_info.get(r["player_key"], {})
        r["player_name"] = info.get("name", r["player_key"])
        r["player_position"] = info.get("position", "")

    return results


def fetch_league_settings(league_key: str) -> dict:
    """Fetch league settings including FAAB budget."""
    data = yahoo_api_get(f"/league/{league_key}/settings")
    settings = data["fantasy_content"]["league"][1]["settings"][0]

    faab_budget = 100  # default
    # Look for waiver settings
    if "waiver_rule" in settings:
        # Some leagues store budget in different places
        pass

    # Check max_adds or budget
    for key in ("budget", "salary_cap", "waiver_budget"):
        if key in settings:
            try:
                faab_budget = int(settings[key])
            except (ValueError, TypeError):
                pass

    return {
        "faab_budget": faab_budget,
        "settings_raw": settings,
    }


def fetch_transactions_full(league_key: str) -> dict:
    """Fetch all transactions with full player details for a league."""
    data = yahoo_api_get(f"/league/{league_key}/transactions")
    tx_data = data["fantasy_content"]["league"][1]["transactions"]
    count = tx_data.get("count", 0)

    transactions = []
    for i in range(count):
        tx_raw = tx_data[str(i)]["transaction"]
        meta = tx_raw[0] if isinstance(tx_raw, list) else tx_raw
        players_section = tx_raw[1] if isinstance(tx_raw, list) and len(tx_raw) > 1 else {}

        tx_entry = {
            "transaction_id": meta.get("transaction_id", ""),
            "type": meta.get("type", ""),
            "status": meta.get("status", ""),
            "timestamp": meta.get("timestamp", ""),
            "faab_bid": None,
            "players": [],
        }

        if "faab_bid" in meta:
            tx_entry["faab_bid"] = int(meta["faab_bid"])

        if "players" in players_section:
            players_data = players_section["players"]
            p_count = players_data.get("count", 0)
            for j in range(p_count):
                p_raw = players_data[str(j)]["player"]
                player_info = _parse_tx_player(p_raw)
                tx_entry["players"].append(player_info)

        transactions.append(tx_entry)

    return {"transactions": transactions}


def _parse_yahoo_team(team_raw) -> dict:
    """Parse team info from Yahoo's nested list/dict format."""
    info = {"name": "", "team_key": "", "manager": ""}
    items = team_raw if isinstance(team_raw, list) else [team_raw]
    for item in items:
        if isinstance(item, dict):
            if "name" in item:
                info["name"] = item["name"]
            if "team_key" in item:
                info["team_key"] = item["team_key"]
            if "managers" in item:
                mgrs = item["managers"]
                if isinstance(mgrs, list) and mgrs:
                    info["manager"] = mgrs[0]["manager"].get("nickname", "")
        elif isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    if "name" in sub:
                        info["name"] = sub["name"]
                    if "team_key" in sub:
                        info["team_key"] = sub["team_key"]
                    if "managers" in sub:
                        mgrs = sub["managers"]
                        if isinstance(mgrs, list) and mgrs:
                            info["manager"] = mgrs[0]["manager"].get("nickname", "")
    return info


def _batch_resolve_players(league_key: str, player_keys: list[str]) -> dict[str, dict]:
    """Resolve player names and positions in batches of 25."""
    result = {}
    batch_size = 25

    for i in range(0, len(player_keys), batch_size):
        batch = player_keys[i:i + batch_size]
        keys_str = ",".join(batch)
        try:
            data = yahoo_api_get(f"/league/{league_key}/players;player_keys={keys_str}")
            players_data = data["fantasy_content"]["league"][1]["players"]
            p_count = players_data.get("count", 0)
            for j in range(p_count):
                p_raw = players_data[str(j)]["player"]
                info = _parse_player_basic(p_raw)
                result[info["player_key"]] = info
        except Exception as e:
            print(f"[YahooService] Player batch resolve failed: {e}", flush=True)

    return result


def _parse_player_basic(player_raw) -> dict:
    """Parse basic player info (name, position, key) from Yahoo format."""
    info = {"player_key": "", "name": "", "position": ""}
    items = player_raw[0] if isinstance(player_raw, list) else [player_raw]

    for item in items:
        if isinstance(item, dict):
            if "player_key" in item:
                info["player_key"] = item["player_key"]
            if "name" in item:
                name_data = item["name"]
                info["name"] = name_data.get("full", "")
            if "display_position" in item:
                info["position"] = item["display_position"]
            if "eligible_positions" in item:
                positions = item["eligible_positions"]
                if isinstance(positions, list):
                    pos_list = []
                    for p in positions:
                        if isinstance(p, dict) and "position" in p:
                            pos_list.append(p["position"])
                    if pos_list:
                        info["position"] = ",".join(pos_list)

    return info


def _parse_tx_player(player_raw) -> dict:
    """Parse player info from transaction data."""
    info_list = player_raw[0] if isinstance(player_raw, list) else [player_raw]
    tx_data = player_raw[1] if isinstance(player_raw, list) and len(player_raw) > 1 else {}

    player = {
        "name": "",
        "player_key": "",
        "position": "",
        "editorial_team": "",
        "transaction_type": "",
        "source_type": "",
        "destination_type": "",
        "source_team_key": "",
        "destination_team_key": "",
        "source_team_name": "",
        "destination_team_name": "",
    }

    for item in info_list:
        if isinstance(item, dict):
            if "player_key" in item:
                player["player_key"] = item["player_key"]
            if "name" in item:
                player["name"] = item["name"].get("full", "")
            if "display_position" in item:
                player["position"] = item["display_position"]
            if "editorial_team_abbr" in item:
                player["editorial_team"] = item["editorial_team_abbr"]

    if isinstance(tx_data, dict) and "transaction_data" in tx_data:
        td = tx_data["transaction_data"]
        if isinstance(td, list):
            td = td[0] if td else {}
        player["transaction_type"] = td.get("type", "")
        player["source_type"] = td.get("source_type", "")
        player["destination_type"] = td.get("destination_type", "")
        player["source_team_key"] = td.get("source_team_key", "")
        player["destination_team_key"] = td.get("destination_team_key", "")
        player["source_team_name"] = td.get("source_team_name", "")
        player["destination_team_name"] = td.get("destination_team_name", "")

    return player


def get_token_status() -> dict:
    """
    Get current Yahoo token connection status for dashboard display.

    Returns dict with: connected, user_id, yahoo_guid, expires_at,
                       is_expired, updated_at, message
    """
    from api.database import get_commissioner_yahoo_token

    token_row = get_commissioner_yahoo_token()

    if not token_row:
        return {
            "connected": False,
            "user_id": None,
            "yahoo_guid": "",
            "expires_at": None,
            "is_expired": False,
            "updated_at": None,
            "message": "Yahoo API 尚未連結 Not connected",
        }

    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = token_row.get("expires_at")
    is_expired = False

    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        is_expired = now >= expires_at

    updated_at = token_row.get("updated_at")

    return {
        "connected": True,
        "user_id": token_row.get("user_id"),
        "yahoo_guid": token_row.get("yahoo_guid", ""),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "is_expired": is_expired,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "message": (
            "Token 已過期，請重新整理或重新登入 Token expired"
            if is_expired
            else "Yahoo API 已連結 Connected"
        ),
    }
