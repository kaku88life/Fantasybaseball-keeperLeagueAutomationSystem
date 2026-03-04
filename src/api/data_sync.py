"""
Fantasy Baseball Keeper League - Data Sync Module

Integrates Yahoo API data with local Excel contract data.

Key responsibilities:
  - Match Excel players to Yahoo players by name
  - Enrich contract data with Yahoo player IDs and real-time info
  - Cross-validate rosters between Excel and Yahoo
  - Build unified LeagueState combining both data sources
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.yahoo_client import YahooFantasyClient
from src.contract.models import (
    ContractType,
    LeagueState,
    Player,
    Team,
)
from src.parser.normalizer import (
    normalize_player_name,
    normalize_player_name_for_matching,
)


class DataSync:
    """Synchronizes Excel contract data with Yahoo Fantasy API."""

    def __init__(self, yahoo_client: Optional[YahooFantasyClient] = None):
        self.client = yahoo_client or YahooFantasyClient()
        self._yahoo_teams: dict[str, list[dict]] = {}  # league_key -> teams
        self._yahoo_rosters: dict[str, list[dict]] = {}  # team_key -> roster

    # ========== Yahoo Data Fetching ==========

    def fetch_yahoo_teams(self, league_key: Optional[str] = None) -> list[dict]:
        """Fetch all teams from Yahoo for a league."""
        lk = league_key or self.client.league_id
        teams = self.client.get_teams(league_key=lk)
        self._yahoo_teams[lk] = teams
        return teams

    def fetch_yahoo_roster(
        self,
        team_number: str,
        league_key: Optional[str] = None,
    ) -> list[dict]:
        """Fetch a team's roster from Yahoo."""
        lk = league_key or self.client.league_id
        team_key = f"{lk}.t.{team_number}"
        roster = self.client.get_roster(team_number, league_key=lk)
        self._yahoo_rosters[team_key] = roster
        return roster

    def fetch_all_rosters(self, league_key: Optional[str] = None) -> dict[str, list[dict]]:
        """Fetch all 16 team rosters from Yahoo."""
        lk = league_key or self.client.league_id
        teams = self.fetch_yahoo_teams(lk)
        rosters = {}
        for t in teams:
            team_key = t["team_key"]
            team_num = team_key.split(".")[-1]
            roster = self.fetch_yahoo_roster(team_num, league_key=lk)
            rosters[team_key] = roster
        return rosters

    # ========== Name Matching ==========

    @staticmethod
    def match_player_name(excel_name: str, yahoo_name: str) -> float:
        """
        Calculate name match score between Excel and Yahoo player names.

        Returns:
            Score 0.0 to 1.0 (1.0 = exact match)
        """
        e = normalize_player_name_for_matching(excel_name)
        y = normalize_player_name_for_matching(yahoo_name)

        if not e or not y:
            return 0.0

        # Exact match
        if e == y:
            return 1.0

        # One contains the other (handle "Shohei Ohtani" vs "Shohei Ohtani (Pitcher)")
        if e in y or y in e:
            return 0.95

        # Split into parts and compare
        e_parts = set(e.split())
        y_parts = set(y.split())

        if not e_parts or not y_parts:
            return 0.0

        # All parts of the shorter name appear in the longer name
        shorter = e_parts if len(e_parts) <= len(y_parts) else y_parts
        longer = e_parts if len(e_parts) > len(y_parts) else y_parts
        if shorter.issubset(longer):
            return 0.9

        # Overlap ratio
        overlap = len(e_parts & y_parts)
        total = max(len(e_parts), len(y_parts))
        return overlap / total if total > 0 else 0.0

    def find_yahoo_match(
        self,
        excel_player: Player,
        yahoo_roster: list[dict],
        threshold: float = 0.8,
    ) -> Optional[dict]:
        """
        Find the best matching Yahoo player for an Excel player.

        Args:
            excel_player: Player from Excel data
            yahoo_roster: List of Yahoo player dicts
            threshold: Minimum match score

        Returns:
            Best matching Yahoo player dict, or None
        """
        best_match = None
        best_score = 0.0

        for yp in yahoo_roster:
            score = self.match_player_name(excel_player.name, yp["name"])
            if score > best_score:
                best_score = score
                best_match = yp

        if best_score >= threshold:
            return best_match
        return None

    # ========== Roster Comparison ==========

    def compare_rosters(
        self,
        excel_team: Team,
        yahoo_roster: list[dict],
    ) -> dict:
        """
        Compare Excel keeper roster with Yahoo full roster.

        Returns:
            {
                "matched": [(excel_player, yahoo_player, score), ...],
                "excel_only": [excel_player, ...],  # in Excel but not Yahoo
                "yahoo_only": [yahoo_player, ...],   # in Yahoo but not Excel
            }
        """
        matched = []
        excel_only = []
        yahoo_matched_keys = set()

        for ep in excel_team.players:
            yp = self.find_yahoo_match(ep, yahoo_roster)
            if yp:
                score = self.match_player_name(ep.name, yp["name"])
                matched.append((ep, yp, score))
                yahoo_matched_keys.add(yp["player_key"])
            else:
                excel_only.append(ep)

        yahoo_only = [
            yp for yp in yahoo_roster
            if yp["player_key"] not in yahoo_matched_keys
        ]

        return {
            "matched": matched,
            "excel_only": excel_only,
            "yahoo_only": yahoo_only,
        }

    # ========== Team Matching ==========

    def match_teams(
        self,
        excel_teams: list[Team],
        yahoo_teams: list[dict],
    ) -> list[dict]:
        """
        Match Excel teams to Yahoo teams by manager name mapping,
        direct name match, or team name match.

        Returns:
            List of dicts: {excel_team, yahoo_team, match_type}
        """
        from config.settings import MANAGER_NAME_MAPPING

        matches = []
        matched_yahoo_keys = set()

        for et in excel_teams:
            best_yt = None
            match_type = None

            # 1. Try explicit mapping first
            mapped_name = MANAGER_NAME_MAPPING.get(et.manager_name, "")
            if mapped_name:
                mapped_lower = normalize_player_name_for_matching(mapped_name)
                for yt in yahoo_teams:
                    if yt["team_key"] in matched_yahoo_keys:
                        continue
                    y_mgr = normalize_player_name_for_matching(yt.get("manager", ""))
                    if mapped_lower and y_mgr and (mapped_lower in y_mgr or y_mgr in mapped_lower):
                        best_yt = yt
                        match_type = "mapping"
                        break

            # 2. Try direct manager name match
            if not best_yt:
                e_mgr = normalize_player_name_for_matching(et.manager_name)
                for yt in yahoo_teams:
                    if yt["team_key"] in matched_yahoo_keys:
                        continue
                    y_mgr = normalize_player_name_for_matching(yt.get("manager", ""))
                    if e_mgr and y_mgr and (e_mgr in y_mgr or y_mgr in e_mgr):
                        best_yt = yt
                        match_type = "manager"
                        break

            # 3. Try team name match
            if not best_yt:
                e_team = normalize_player_name_for_matching(et.team_name)
                for yt in yahoo_teams:
                    if yt["team_key"] in matched_yahoo_keys:
                        continue
                    y_team = normalize_player_name_for_matching(yt.get("name", ""))
                    if e_team and y_team and (e_team in y_team or y_team in e_team):
                        best_yt = yt
                        match_type = "team_name"
                        break

            if best_yt:
                matched_yahoo_keys.add(best_yt["team_key"])

            matches.append({
                "excel_team": et,
                "yahoo_team": best_yt,
                "match_type": match_type,
            })

        return matches

    # ========== Enrichment ==========

    def enrich_team_with_yahoo(
        self,
        excel_team: Team,
        yahoo_roster: list[dict],
    ) -> Team:
        """
        Enrich Excel team data with Yahoo player IDs and positions.

        Modifies excel_team in place and returns it.
        """
        for ep in excel_team.players:
            yp = self.find_yahoo_match(ep, yahoo_roster)
            if yp:
                ep.yahoo_player_id = yp["player_key"]
                # Update position from Yahoo if more complete
                if yp["position"] and len(yp["position"]) > len(ep.position):
                    ep.position = yp["position"]

        return excel_team

    # ========== Full Sync ==========

    def sync_league(
        self,
        excel_teams: list[Team],
        year: int,
        league_key: Optional[str] = None,
    ) -> dict:
        """
        Full sync: match Excel teams to Yahoo, enrich with API data.

        Args:
            excel_teams: Teams from Excel import
            year: Season year
            league_key: Override Yahoo league key

        Returns:
            {
                "league_state": LeagueState,
                "team_matches": [...],
                "sync_report": {...},
            }
        """
        lk = league_key
        if not lk:
            # Try to find the correct league key for this year
            try:
                lk = self.client.get_league_key(year)
            except (ValueError, RuntimeError):
                lk = self.client.league_id

        # Fetch Yahoo data
        yahoo_teams = self.fetch_yahoo_teams(lk)
        team_matches = self.match_teams(excel_teams, yahoo_teams)

        total_matched_players = 0
        total_excel_only = 0
        total_yahoo_only = 0
        enriched_teams = []

        for tm in team_matches:
            et = tm["excel_team"]
            yt = tm["yahoo_team"]

            if yt:
                team_num = yt["team_key"].split(".")[-1]
                yahoo_roster = self.fetch_yahoo_roster(team_num, league_key=lk)

                # Enrich and compare
                self.enrich_team_with_yahoo(et, yahoo_roster)
                comparison = self.compare_rosters(et, yahoo_roster)

                tm["comparison"] = comparison
                total_matched_players += len(comparison["matched"])
                total_excel_only += len(comparison["excel_only"])
                total_yahoo_only += len(comparison["yahoo_only"])

                # Set Yahoo team info
                et.yahoo_team_id = yt["team_key"]
                if not et.team_name:
                    et.team_name = yt["name"]

            enriched_teams.append(et)

        league_state = LeagueState(year=year, teams=enriched_teams)

        sync_report = {
            "year": year,
            "league_key": lk,
            "teams_matched": sum(1 for tm in team_matches if tm["yahoo_team"]),
            "teams_unmatched": sum(1 for tm in team_matches if not tm["yahoo_team"]),
            "players_matched": total_matched_players,
            "players_excel_only": total_excel_only,
            "players_yahoo_only": total_yahoo_only,
        }

        return {
            "league_state": league_state,
            "team_matches": team_matches,
            "sync_report": sync_report,
        }

    # ========== Draft Price Sync ==========

    def get_draft_prices(
        self,
        year: int,
        league_key: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Get draft prices (auction costs) for all players in a year.

        Returns:
            Dict mapping player_key -> cost
        """
        lk = league_key
        if not lk:
            try:
                lk = self.client.get_league_key(year)
            except (ValueError, RuntimeError):
                lk = self.client.league_id

        results = self.client.get_draft_results(league_key=lk)
        return {r["player_key"]: r["cost"] for r in results if r["cost"] > 0}

    # ========== Report ==========

    def print_sync_report(self, sync_result: dict):
        """Print a human-readable sync report."""
        report = sync_result["sync_report"]
        matches = sync_result["team_matches"]

        print(f"\n{'=' * 60}")
        print(f" Data Sync Report - {report['year']} Season")
        print(f" League Key: {report['league_key']}")
        print(f"{'=' * 60}")

        print(f"\n Teams: {report['teams_matched']} matched, "
              f"{report['teams_unmatched']} unmatched")
        print(f" Players: {report['players_matched']} matched, "
              f"{report['players_excel_only']} Excel-only, "
              f"{report['players_yahoo_only']} Yahoo-only")

        for tm in matches:
            et = tm["excel_team"]
            yt = tm["yahoo_team"]
            comp = tm.get("comparison")

            yahoo_name = yt["name"] if yt else "(unmatched)"
            match_type = tm["match_type"] or ""

            print(f"\n  {et.manager_name} -> {yahoo_name} [{match_type}]")

            if comp:
                if comp["excel_only"]:
                    print(f"    Excel only (keepers not on Yahoo roster):")
                    for ep in comp["excel_only"]:
                        print(f"      - {ep.name} ({ep.contract.display})")
                if comp["yahoo_only"]:
                    non_keeper_count = len(comp["yahoo_only"])
                    print(f"    Yahoo only: {non_keeper_count} players "
                          f"(non-keeper / drafted)")

        print(f"\n{'=' * 60}")
