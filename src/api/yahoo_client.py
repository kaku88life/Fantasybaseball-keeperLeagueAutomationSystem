"""
Fantasy Baseball Keeper League - Yahoo Fantasy API Client

Direct REST API wrapper using requests + OAuth2 token management.
Supports multi-year league key mapping for keeper league history.

Capabilities:
  - League info, standings, settings
  - Team rosters with positions
  - Draft results with auction prices
  - Transactions (adds, drops, trades)
  - Token auto-refresh
  - Multi-year league key resolution
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


class YahooFantasyClient:
    """Yahoo Fantasy Sports API wrapper for Fantasy Baseball."""

    def __init__(
        self,
        league_id: Optional[str] = None,
        oauth_file: Optional[str] = None,
    ):
        """
        Initialize Yahoo API client.

        Args:
            league_id: Yahoo league ID (e.g., "469.l.80910").
                       Falls back to YAHOO_LEAGUE_ID env var.
            oauth_file: Path to oauth2.json. Defaults to project root.
        """
        self.league_id = league_id or os.getenv("YAHOO_LEAGUE_ID")
        self._oauth_file = Path(
            oauth_file
            or Path(__file__).resolve().parent.parent.parent / "oauth2.json"
        )
        self._creds: dict = {}
        self._token_expiry: float = 0

        # Multi-year league key cache {year: league_key}
        self._league_keys: dict[int, str] = {}

    # ========== Auth ==========

    def _load_creds(self) -> dict:
        """Load OAuth2 credentials from file."""
        if not self._oauth_file.exists():
            raise FileNotFoundError(
                f"OAuth2 file not found: {self._oauth_file}\n"
                "Run: python scripts/yahoo_auth.py"
            )
        self._creds = json.loads(self._oauth_file.read_text())
        return self._creds

    def _save_creds(self):
        """Save updated credentials (after token refresh)."""
        self._oauth_file.write_text(json.dumps(self._creds, indent=2))

    def _ensure_token(self):
        """Ensure we have a valid access token, refreshing if needed."""
        if not self._creds:
            self._load_creds()

        if not self._creds.get("access_token"):
            raise ValueError(
                "No access token found. Run: python scripts/yahoo_auth.py"
            )

        # Refresh if token is about to expire (or we don't know expiry)
        if time.time() >= self._token_expiry - 60:
            self._refresh_token()

    def _refresh_token(self):
        """Refresh the access token using refresh_token."""
        refresh_token = self._creds.get("refresh_token")
        if not refresh_token:
            raise ValueError(
                "No refresh token. Re-authorize: python scripts/yahoo_auth.py"
            )

        client_id = self._creds.get("consumer_key", os.getenv("YAHOO_CLIENT_ID"))
        client_secret = self._creds.get(
            "consumer_secret", os.getenv("YAHOO_CLIENT_SECRET")
        )

        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=HTTPBasicAuth(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Token refresh failed ({resp.status_code}): {resp.text}"
            )

        token_data = resp.json()
        self._creds["access_token"] = token_data["access_token"]
        if "refresh_token" in token_data:
            self._creds["refresh_token"] = token_data["refresh_token"]
        self._token_expiry = time.time() + token_data.get("expires_in", 3600)
        self._save_creds()

    def _headers(self) -> dict:
        """Get request headers with current access token."""
        self._ensure_token()
        return {"Authorization": f"Bearer {self._creds['access_token']}"}

    # ========== HTTP helpers ==========

    def _get(self, path: str) -> dict:
        """
        GET request to Yahoo Fantasy API with auto-retry on 401.

        Args:
            path: API path (e.g., "/league/469.l.80910")

        Returns:
            Parsed JSON response
        """
        url = f"{BASE_URL}{path}"
        separator = "&" if "?" in url else "?"
        url += f"{separator}format=json"

        resp = requests.get(url, headers=self._headers())

        # Retry once on 401 (token expired mid-request)
        if resp.status_code == 401:
            self._token_expiry = 0
            resp = requests.get(url, headers=self._headers())

        if resp.status_code != 200:
            raise RuntimeError(
                f"API request failed ({resp.status_code}): {resp.text[:300]}"
            )

        return resp.json()

    # ========== Multi-year League Keys ==========

    def discover_league_keys(self) -> dict[int, str]:
        """
        Discover all "5-Man MLB Keeper" league keys across years.

        Returns:
            Dict mapping year -> league_key
        """
        import re

        data = self._get("/users;use_login=1/games;game_codes=mlb/leagues")
        raw = json.dumps(data, ensure_ascii=False)

        # Known MLB game_key -> season mapping
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

        self._league_keys = league_keys
        return league_keys

    def get_league_key(self, year: int) -> str:
        """
        Get league key for a specific year.

        Args:
            year: Season year (e.g., 2025)

        Returns:
            League key string (e.g., "458.l.40288")
        """
        if not self._league_keys:
            self.discover_league_keys()

        if year not in self._league_keys:
            raise ValueError(
                f"No league found for year {year}. "
                f"Available: {sorted(self._league_keys.keys())}"
            )
        return self._league_keys[year]

    # ========== League Info ==========

    def get_league_info(self, league_key: Optional[str] = None) -> dict:
        """Get basic league information."""
        lk = league_key or self.league_id
        data = self._get(f"/league/{lk}")
        return data["fantasy_content"]["league"][0]

    def get_league_settings(self, league_key: Optional[str] = None) -> dict:
        """Get league settings (roster positions, scoring, etc.)."""
        lk = league_key or self.league_id
        data = self._get(f"/league/{lk}/settings")
        return data["fantasy_content"]["league"][1]["settings"][0]

    def get_standings(self, league_key: Optional[str] = None) -> list[dict]:
        """
        Get league standings.

        Returns:
            List of team dicts with rank, name, manager, record
        """
        lk = league_key or self.league_id
        data = self._get(f"/league/{lk}/standings")
        standings_data = data["fantasy_content"]["league"][1]["standings"][0]["teams"]
        count = standings_data["count"]

        teams = []
        for i in range(count):
            team_raw = standings_data[str(i)]["team"]
            info = self._parse_team_info(team_raw[0])
            standing = team_raw[1].get("team_standings", {})
            info["rank"] = standing.get("rank")
            record = standing.get("outcome_totals", {})
            info["wins"] = record.get("wins")
            info["losses"] = record.get("losses")
            info["ties"] = record.get("ties")
            teams.append(info)

        return teams

    # ========== Teams ==========

    def get_teams(self, league_key: Optional[str] = None) -> list[dict]:
        """Get all teams in the league."""
        lk = league_key or self.league_id
        data = self._get(f"/league/{lk}/teams")
        teams_data = data["fantasy_content"]["league"][1]["teams"]
        count = teams_data["count"]

        teams = []
        for i in range(count):
            team_raw = teams_data[str(i)]["team"][0]
            teams.append(self._parse_team_info(team_raw))
        return teams

    def get_roster(
        self,
        team_key: str,
        league_key: Optional[str] = None,
    ) -> list[dict]:
        """
        Get a team's roster.

        Args:
            team_key: Team key (e.g., "458.l.40288.t.1") or team number (e.g., "1")
            league_key: Override league key

        Returns:
            List of player dicts
        """
        lk = league_key or self.league_id

        # Support bare team number
        if "." not in str(team_key):
            team_key = f"{lk}.t.{team_key}"

        data = self._get(f"/team/{team_key}/roster")
        roster_data = data["fantasy_content"]["team"][1]["roster"]
        players_raw = roster_data["0"]["players"]

        # Handle empty roster (predraft)
        if isinstance(players_raw, list) and len(players_raw) == 0:
            return []

        players = []
        count = players_raw.get("count", 0)
        for i in range(count):
            player_raw = players_raw[str(i)]["player"]
            players.append(self._parse_player(player_raw))
        return players

    # ========== Draft ==========

    def get_draft_results(self, league_key: Optional[str] = None) -> list[dict]:
        """
        Get draft results with auction prices.

        Returns:
            List of dicts: {round, pick, team_key, player_key, cost}
        """
        lk = league_key or self.league_id
        data = self._get(f"/league/{lk}/draftresults")
        dr_data = data["fantasy_content"]["league"][1]["draft_results"]
        count = dr_data["count"]

        results = []
        for i in range(count):
            pick = dr_data[str(i)]["draft_result"]
            results.append({
                "round": int(pick.get("round", 0)),
                "pick": int(pick.get("pick", 0)),
                "team_key": pick.get("team_key", ""),
                "player_key": pick.get("player_key", ""),
                "cost": int(pick.get("cost", 0)),
            })
        return results

    # ========== Transactions ==========

    def get_transactions(
        self,
        league_key: Optional[str] = None,
        transaction_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Get league transactions.

        Args:
            league_key: Override league key
            transaction_type: Filter by type ("add", "drop", "trade", "commish")

        Returns:
            List of transaction summary dicts
        """
        lk = league_key or self.league_id
        data = self._get(f"/league/{lk}/transactions")
        tx_data = data["fantasy_content"]["league"][1]["transactions"]
        count = tx_data["count"]

        transactions = []
        for i in range(count):
            tx = tx_data[str(i)]["transaction"]
            info = tx[0] if isinstance(tx, list) else tx
            entry = {
                "type": info.get("type", ""),
                "status": info.get("status", ""),
                "timestamp": info.get("timestamp", ""),
            }
            if transaction_type and entry["type"] != transaction_type:
                continue
            transactions.append(entry)

        return transactions

    # ========== Parsers ==========

    @staticmethod
    def _parse_team_info(team_raw) -> dict:
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
                                info["manager"] = mgrs[0]["manager"].get(
                                    "nickname", ""
                                )
        return info

    @staticmethod
    def _parse_player(player_raw) -> dict:
        """Parse player data from Yahoo's nested format."""
        info_list = player_raw[0]
        player = {
            "name": "",
            "player_key": "",
            "position": "",
            "team": "",
            "selected_position": "",
            "status": "",
        }

        for item in info_list:
            if isinstance(item, dict):
                if "name" in item:
                    player["name"] = item["name"].get("full", "")
                if "player_key" in item:
                    player["player_key"] = item["player_key"]
                if "display_position" in item:
                    player["position"] = item["display_position"]
                if "editorial_team_abbr" in item:
                    player["team"] = item["editorial_team_abbr"]
                if "status" in item:
                    player["status"] = item["status"]

        # Selected position (where they're slotted on roster)
        if len(player_raw) > 1 and isinstance(player_raw[1], dict):
            sp_data = player_raw[1].get("selected_position", [])
            if isinstance(sp_data, list):
                for s in sp_data:
                    if isinstance(s, dict) and "position" in s:
                        player["selected_position"] = s["position"]

        return player

    # ========== Utility ==========

    def test_connection(self) -> dict:
        """
        Test API connection and return basic league info.

        Returns:
            Dict with connection status and league details
        """
        result = {
            "status": "error",
            "message": "",
            "league_id": self.league_id,
        }

        try:
            league = self.get_league_info()
            teams = self.get_teams()

            result["status"] = "success"
            result["message"] = "Connected successfully"
            result["league_name"] = league.get("name", "Unknown")
            result["season"] = league.get("season", "Unknown")
            result["num_teams"] = league.get("num_teams", len(teams))
            result["draft_status"] = league.get("draft_status", "Unknown")
            result["teams"] = [
                {"name": t["name"], "key": t["team_key"], "manager": t["manager"]}
                for t in teams
            ]
        except Exception as e:
            result["message"] = str(e)

        return result
