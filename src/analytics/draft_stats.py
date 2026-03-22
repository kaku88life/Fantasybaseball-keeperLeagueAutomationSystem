"""
Draft, FAAB, salary, and contract analytics.

Data sources:
  - data/yahoo_{year}_draft.json         Yahoo draft picks
  - data/yahoo_{year}_transactions.json   Yahoo transactions (FAAB, trades)
  - data/historical_keepers.json          2023-2025 keeper lists from Excel
  - data/2026_contracts_v2.json           2026 contract data (all 500 players)
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _normalize_player_name(name: str) -> str:
    """Normalize player name for matching: strip accents, suffixes, punctuation."""
    import unicodedata
    # Remove parenthetical suffixes like "(Pitcher)"
    name = re.sub(r"\s*\(.*?\)\s*", "", name)
    # Strip trailing dots and whitespace
    name = name.strip().rstrip(".")
    # Normalize unicode accents (é -> e, í -> i, etc.)
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# ------------------------------------------------------------------
# Manager name normalization (Excel aliases -> Yahoo aliases)
# ------------------------------------------------------------------
_MGR_NORMALIZE: dict[str, str] = {
    "hyc莊翔宇": "hyc莊翔宇",
    "林小伯": "林小伯",
    "James Chen": "James Chen",
    "郭子睿(Rangers)": "郭子睿(Rangers)",
    "Issac": "Issac",
}

# Manager succession: old -> new (team takeover)
_MGR_SUCCESSION: dict[str, str] = {
    "hyc莊翔宇": "Hank",
    "林小伯": "Billy WU",
}


def _available_years() -> list[int]:
    """Find years with draft data files."""
    years = []
    for f in DATA_DIR.glob("yahoo_*_draft.json"):
        try:
            year = int(f.stem.split("_")[1])
            years.append(year)
        except (IndexError, ValueError):
            pass
    return sorted(years)


def _build_position_lookup() -> dict[str, str]:
    """Build a player_name -> position lookup from contracts data and DB."""
    # Manual fallback for players no longer on any roster or missing from data files
    lookup: dict[str, str] = {
        # Pitchers - SP
        "Max Scherzer": "SP", "Joe Musgrove": "SP", "Kenta Maeda": "SP",
        "Aaron Civale": "SP", "Chris Bassitt": "SP", "Triston McKenzie": "SP",
        "Nestor Cortes": "SP", "Miles Mikolas": "SP", "José Urquidy": "SP",
        "Michael Soroka": "SP", "Jon Gray": "SP", "Patrick Sandoval": "SP",
        "Marcus Stroman": "SP", "Cal Quantrill": "SP", "Noah Syndergaard": "SP",
        "Carlos Carrasco": "SP", "Steven Matz": "SP", "Julio Urías": "SP",
        "Dane Dunning": "SP", "Louis Varland": "SP", "Kutter Crawford": "SP",
        "Graham Ashcraft": "SP", "Jordan Wicks": "SP", "Adbert Alzolay": "SP",
        "Brock Stewart": "SP", "Andre Pallante": "SP", "Roansy Contreras": "SP",
        "Frankie Montas": "SP", "James Paxton": "SP", "Wade Miley": "SP",
        "Adam Wainwright": "SP", "Johnny Cueto": "SP", "Corey Kluber": "SP",
        "Ross Stripling": "SP", "Alex Cobb": "SP", "Drew Rucinski": "SP",
        "Collin McHugh": "SP", "Hayden Wesneski": "SP", "Gordon Graceffo": "SP",
        "Shintaro Fujinami": "SP", "Drey Jameson": "SP", "Jared Shuster": "SP",
        "JP Sears": "SP", "Erick Fedde": "SP", "Bowden Francis": "SP",
        "DJ Herz": "SP", "Tobias Myers": "SP", "David Festa": "SP",
        "Hayden Birdsong": "SP", "Cody Bradford": "SP", "Ben Brown": "SP",
        "Griffin Canning": "SP", "Kyle Gibson": "SP", "Daniel Espino": "SP",
        "Sixto Sánchez": "SP", "Cole Winn": "SP", "Chase Petty": "SP",
        "Grant Holmes": "SP", "Chase Hampton": "SP", "Noah Schultz": "SP",
        "Frank Mozzicato": "SP", "Robert Gasser": "SP", "Beau Brieske": "SP",
        "José Suarez": "SP", "José Buttó": "SP",
        # Pitchers - RP
        "Paul Sewald": "RP", "Craig Kimbrel": "RP", "Giovanny Gallegos": "RP",
        "Jorge López": "RP", "A.J. Minter": "RP", "Adam Ottavino": "RP",
        "Liam Hendriks": "RP", "Cionel Pérez": "RP", "Kendall Graveman": "RP",
        "Erik Swanson": "RP", "Andrew Chafin": "RP", "Brad Boxberger": "RP",
        "Ryne Stanek": "RP", "James Karinchak": "RP", "Brock Burke": "RP",
        "John Schreiber": "RP", "Génesis Cabrera": "RP", "Michael Fulmer": "RP",
        "Joe Mantiply": "RP", "Daniel Hudson": "RP", "Anthony Bass": "RP",
        "Dylan Floro": "RP", "Jimmy Herget": "RP", "Rafael Montero": "RP",
        "Jonathan Loáisiga": "RP", "Trevor May": "RP", "Brandon Hughes": "RP",
        "Brusdar Graterol": "RP", "Taylor Rogers": "RP", "Adam Cimber": "RP",
        "Héctor Neris": "RP", "Brad Hand": "RP", "J.P. Feyereisen": "RP",
        "José Alvarado": "RP", "Kevin Ginkel": "RP", "Yuki Matsui": "RP",
        "Yimi García": "RP", "Tim Mayza": "RP", "Andrew Nardi": "RP",
        "Colin Poche": "RP", "Jason Foley": "RP", "Alex Lange": "RP",
        "Joel Payamps": "RP", "Danny Coulombe": "RP", "DL Hall": "RP",
        "Julian Merryweather": "RP", "Caleb Ferguson": "RP", "Colin Holderman": "RP",
        "James McArthur": "RP", "Robert Stephenson": "RP", "Brooks Raley": "RP",
        "Yency Almonte": "RP", "Enyel De Los Santos": "RP", "Jose Cuas": "RP",
        "Shelby Miller": "RP", "Justin Lawrence": "RP", "Hunter Harvey": "RP",
        "Dylan Lee": "RP", "Fernando Cruz": "RP", "Porter Hodge": "RP",
        "Ben Joyce": "RP", "Ryan Brasier": "RP", "Chad Green": "RP",
        "Tommy Kahnle": "RP", "Nate Pearson": "RP", "Kevin Kelly": "RP",
        "Bryan Hudson": "RP", "Justin Slaten": "RP", "Erik Miller": "RP",
        "Elvis Luciano": "RP", "José Leclerc": "RP",
        # Catchers
        "Keibert Ruiz": "C", "Travis d'Arnaud": "C", "Danny Jansen": "C",
        "Eric Haase": "C", "Tyler Stephenson": "C", "Luis Campusano": "C",
        "Bo Naylor": "C", "Henry Davis": "C", "Francisco Alvarez": "C",
        "Joey Bart": "C", "Ryan Jeffers": "C", "Connor Wong": "C",
        "Ivan Herrera": "C", "Yasmani Grandal": "C",
        # Infielders
        "Ty France": "1B", "Jose Abreu": "1B", "José Abreu": "1B",
        "Rowdy Tellez": "1B", "Anthony Rizzo": "1B", "Carlos Santana": "1B",
        "C.J. Cron": "1B", "Nolan Schanuel": "1B", "Pavin Smith": "1B",
        "Alex Kirilloff": "1B",
        "Jonathan India": "2B", "Jake Cronenworth": "2B", "Kolten Wong": "2B",
        "Jean Segura": "2B", "Vaughn Grissom": "2B", "Nick Gordon": "2B",
        "Ezequiel Duran": "2B", "Michael Massey": "2B",
        "Kris Bryant": "3B", "Justin Turner": "3B", "Gio Urshela": "3B",
        "Brandon Drury": "3B", "Josh Rojas": "3B", "Jeimer Candelario": "3B",
        "Jose Miranda": "3B", "Patrick Wisdom": "3B", "Joey Meneses": "3B",
        "Christian Encarnacion-Strand": "3B",
        "Tim Anderson": "SS", "Amed Rosario": "SS", "Oswald Peraza": "SS",
        "Jon Berti": "SS", "Adalberto Mondesi": "SS", "Jorge Mateo": "SS",
        "Masyn Winn": "SS", "Hyeseong Kim": "SS", "Brooks Lee": "SS",
        "Willi Castro": "SS", "Joey Ortiz": "SS",
        # Outfielders
        "Jesse Winker": "OF", "Eloy Jimenez": "OF", "Eloy Jiménez": "OF",
        "Jake Fraley": "OF", "Starling Marte": "OF", "Jarred Kelenic": "OF",
        "Hunter Renfroe": "OF", "Oscar González": "OF", "Austin Hays": "OF",
        "Dylan Carlson": "OF", "Mitch Haniger": "OF", "Garrett Mitchell": "OF",
        "Seth Brown": "OF", "Joc Pederson": "OF", "Oscar Colás": "OF",
        "Charlie Blackmon": "OF", "Bryan De La Cruz": "OF", "Mark Canha": "OF",
        "Michael Conforto": "OF", "Esteury Ruiz": "OF", "J.D. Martinez": "OF",
        "Yoán Moncada": "3B", "Chris Taylor": "SS,OF",
        "Nelson Cruz": "DH", "Joey Gallo": "OF", "Jared Walsh": "1B",
        "Randal Grichuk": "OF", "Wilmer Flores": "1B", "Eduardo Escobar": "3B",
        "Anthony Rendon": "3B", "Austin Meadows": "OF",
        "Alek Thomas": "OF", "Jack Suwinski": "OF", "Nelson Velázquez": "OF",
        "Luke Raley": "OF", "Will Benson": "OF", "Davis Schneider": "OF",
        "Matt Vierling": "OF", "Luis Matos": "OF", "Max Kepler": "OF",
        "Heston Kjerstad": "OF", "Johan Rojas": "OF", "Leody Taveras": "OF",
        "Jose Siri": "OF", "Nick Loftin": "SS", "Druw Jones": "OF",
        "Curtis Mead": "3B", "Ricky Tiedemann": "SP",
        "Victor Robles": "OF", "JJ Bleday": "OF", "Brandon Marsh": "OF",
        "Tyler Fitzgerald": "SS", "Tommy Pham": "OF", "Jacob Young": "OF",
        "Luisangel Acuña": "SS", "Emmanuel Rodriguez": "OF",
        "Ethan Salas": "C",
        # Multi-position
        "Diego Castillo": "3B", "Yu Chang": "3B",
        "J.D. Davis": "3B", "Dominic Fletcher": "OF",
        "Yusniel Díaz": "OF", "Brandon Drury": "3B",
        "Hunter Dozier": "3B", "Michael Brantley": "OF",
        "Wil Myers": "OF", "Adam Duvall": "OF",
        "Garrett Cooper": "1B", "Luis Urías": "SS",
        "Elvis Andrus": "SS",
    }

    # Source 1: contracts JSON (most reliable, has position field)
    contracts_path = DATA_DIR / "2026_contracts_v2.json"
    if contracts_path.exists():
        try:
            with open(contracts_path, encoding="utf-8") as f:
                contracts = json.load(f)
            for team_name, team_data in contracts.get("teams", {}).items():
                for player in team_data.get("players", []):
                    name = player.get("name", "")
                    pos = player.get("position", "")
                    if name and pos:
                        lookup[name] = pos
        except Exception:
            pass

    # Source 2: historical keepers (has position for many players across years)
    hist_path = DATA_DIR / "historical_keepers.json"
    if hist_path.exists():
        try:
            with open(hist_path, encoding="utf-8") as f:
                hist = json.load(f)
            for _year, managers in hist.items():
                for _mgr, players_list in managers.items():
                    if not isinstance(players_list, list):
                        continue
                    for p in players_list:
                        if not isinstance(p, dict):
                            continue
                        name = p.get("player", "")
                        pos = p.get("position", "")
                        if name and pos and name not in lookup:
                            lookup[name] = pos
        except Exception:
            pass

    # Source 3: Yahoo roster files (has position for all rostered players)
    for roster_file in sorted(DATA_DIR.glob("yahoo_*_rosters.json")):
        try:
            with open(roster_file, encoding="utf-8") as f:
                rosters = json.load(f)
            for _team_key, team_data in rosters.items():
                if not isinstance(team_data, dict):
                    continue
                for p in team_data.get("players", []):
                    name = p.get("name", "")
                    pos = p.get("position", "")
                    if name and pos and name not in lookup:
                        lookup[name] = pos
        except Exception:
            pass

    # Source 4: players DB table (has yahoo position data)
    try:
        from api.database import get_db
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, display_position FROM players WHERE display_position IS NOT NULL")
                for row in cur.fetchall():
                    name, pos = row
                    if name and pos and name not in lookup:
                        lookup[name] = pos
        finally:
            conn.close()
    except Exception:
        pass

    return lookup


def _load_draft(year: int) -> list[dict]:
    path = DATA_DIR / f"yahoo_{year}_draft.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_transactions(year: int) -> list[dict]:
    path = DATA_DIR / f"yahoo_{year}_transactions.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("transactions", [])


def _load_league_meta(year: int) -> dict:
    """Load league metadata (FAAB budget, etc.) if available."""
    path = DATA_DIR / f"yahoo_{year}_league_settings.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# #5: Draft spending analytics
# ------------------------------------------------------------------

def compute_draft_stats(years: list[int] | None = None) -> dict:
    """Compute per-team draft spending with top-10 picks per year.

    Focus: each GM's top 10 most expensive picks to reveal spending habits
    (front-loaded big spenders vs. mid-round concentrated).

    Returns:
        {
            "years": [2025, ...],
            "teams": {
                "manager_name": {
                    "yearly": {
                        "2025": {
                            "top_picks": [
                                {"player": "...", "cost": 72, "round": 1,
                                 "pick": 3, "position": "SP"},
                            ],
                            "top10_total": 350,
                            "total_spent": 300,
                            "players_drafted": 27,
                        },
                    },
                }
            },
            "yearly_summary": {
                "2025": {
                    "league_max": {"cost": 72, "player": "...", "manager": "..."},
                    "team_count": 16,
                }
            }
        }
    """
    if years is None:
        years = _available_years()

    # Build position lookup for enrichment
    pos_lookup = _build_position_lookup()

    all_teams: dict[str, dict] = defaultdict(lambda: {"yearly": {}})
    yearly_summary: dict[str, dict] = {}

    # Load keeper data to exclude keeper players from draft stats
    hist = _load_historical_keepers()

    for year in years:
        draft = _load_draft(year)
        if not draft:
            continue

        year_str = str(year)
        team_picks: dict[str, list[dict]] = defaultdict(list)

        # Build keeper set (historical_keepers + contracts JSON)
        keeper_norm = _build_keeper_set(year, hist)

        league_max = {"cost": 0, "player": "", "manager": ""}

        for pick in draft:
            mgr = pick.get("manager", "Unknown")
            cost = pick.get("cost", 0)
            player = pick.get("player_name", "")
            position = pick.get("player_position", "") or pos_lookup.get(player, "")

            # Skip keeper players - only count actual draft picks
            if _normalize_player_name(player) in keeper_norm:
                continue

            team_picks[mgr].append({
                "round": pick.get("round", 0),
                "pick": pick.get("pick", 0),
                "cost": cost,
                "player": player,
                "position": position,
            })

            if cost > league_max["cost"]:
                league_max = {"cost": cost, "player": player, "manager": mgr}

        # Aggregate per team - top 10 picks by cost
        for mgr, picks in team_picks.items():
            sorted_picks = sorted(picks, key=lambda p: p["cost"], reverse=True)
            top10 = sorted_picks[:10]
            total_spent = sum(p["cost"] for p in picks)

            all_teams[mgr]["yearly"][year_str] = {
                "top_picks": top10,
                "top10_total": sum(p["cost"] for p in top10),
                "total_spent": total_spent,
                "players_drafted": len(picks),
            }

        yearly_summary[year_str] = {
            "team_count": len(team_picks),
            "league_max": league_max,
        }

    return {
        "years": years,
        "teams": dict(all_teams),
        "yearly_summary": yearly_summary,
    }


# ------------------------------------------------------------------
# #5: FAAB analytics
# ------------------------------------------------------------------

def compute_faab_stats(years: list[int] | None = None) -> dict:
    """Compute per-team FAAB spending stats across years.

    Returns:
        {
            "years": [2021, ...],
            "teams": {
                "manager_name": {
                    "yearly": {
                        "2025": {
                            "total_faab_spent": 85, "faab_budget": 100,
                            "remaining": 15, "remaining_pct": 15.0,
                            "num_pickups": 42, "avg_bid": 2.0, "max_bid": 10,
                            "max_bid_player": "...",
                        },
                    },
                }
            },
            "yearly_summary": {...}
        }
    """
    if years is None:
        years = _available_years()

    all_teams: dict[str, dict] = defaultdict(lambda: {"yearly": {}})
    yearly_summary: dict[str, dict] = {}

    for year in years:
        txs = _load_transactions(year)
        meta = _load_league_meta(year)
        # FAAB budget: $200 for 2023-2024, $100 for 2025+
        default_faab = 200 if year <= 2024 else 100
        faab_budget = meta.get("faab_budget", default_faab)

        year_str = str(year)
        team_faab: dict[str, dict] = defaultdict(
            lambda: {"total_spent": 0, "pickups": 0, "bids": [], "top_bid": 0, "top_player": ""}
        )

        # Map team_key -> manager name
        draft = _load_draft(year)
        key_to_mgr: dict[str, str] = {}
        for pick in draft:
            tk = pick.get("team_key", "")
            mgr = pick.get("manager", "")
            if tk and mgr:
                key_to_mgr[tk] = mgr

        for tx in txs:
            bid = tx.get("faab_bid")
            if bid is None or bid == 0:
                continue

            players = tx.get("players", [])
            for p in players:
                if p.get("transaction_type") == "add" and p.get("source_type") == "waivers":
                    dest_key = p.get("destination_team_key", "")
                    mgr = key_to_mgr.get(dest_key, p.get("destination_team_name", "Unknown"))

                    team_faab[mgr]["total_spent"] += bid
                    team_faab[mgr]["pickups"] += 1
                    team_faab[mgr]["bids"].append(bid)
                    if bid > team_faab[mgr]["top_bid"]:
                        team_faab[mgr]["top_bid"] = bid
                        team_faab[mgr]["top_player"] = p.get("name", "")

        # Aggregate
        total_league_faab = 0
        for mgr, fd in team_faab.items():
            remaining = faab_budget - fd["total_spent"]
            avg_bid = round(fd["total_spent"] / fd["pickups"], 1) if fd["pickups"] else 0

            all_teams[mgr]["yearly"][year_str] = {
                "total_faab_spent": fd["total_spent"],
                "faab_budget": faab_budget,
                "remaining": remaining,
                "remaining_pct": round(remaining / faab_budget * 100, 1) if faab_budget else 0,
                "num_pickups": fd["pickups"],
                "avg_bid": avg_bid,
                "max_bid": fd["top_bid"],
                "max_bid_player": fd["top_player"],
            }
            total_league_faab += fd["total_spent"]

        team_count = len(team_faab)
        yearly_summary[year_str] = {
            "faab_budget": faab_budget,
            "total_league_faab_spent": total_league_faab,
            "avg_team_faab_spent": round(total_league_faab / team_count, 1) if team_count else 0,
            "team_count": team_count,
        }

    # FAAB vs standings correlation (per-year)
    faab_vs_standings: dict[str, list[dict]] = {}
    for yr in years:
        standings_path = DATA_DIR / f"{yr}_playoff_standings.json"
        if not standings_path.exists():
            continue
        try:
            with open(standings_path, encoding="utf-8") as f:
                standings_data = json.load(f)
        except Exception:
            continue

        place_map: dict[str, int] = {}
        team_name_map: dict[str, str] = {}
        for s in standings_data.get("standings", []):
            place_map[s["manager"]] = s["place"]
            team_name_map[s["manager"]] = s.get("name", "")

        year_corr: list[dict] = []
        for mgr, tdata in all_teams.items():
            faab_yr = tdata.get("yearly", {}).get(str(yr), {})
            if not faab_yr:
                continue
            resolved = _resolve_manager_name(mgr)
            place = place_map.get(resolved) or place_map.get(mgr)
            if place is None:
                continue
            team_name = team_name_map.get(resolved) or team_name_map.get(mgr, "")
            year_corr.append({
                "manager": resolved,
                "team_name": team_name,
                "faab_spent": faab_yr["total_faab_spent"],
                "num_pickups": faab_yr["num_pickups"],
                "place": place,
                "is_playoff": place <= 8,
            })
        year_corr.sort(key=lambda x: x["place"])
        if year_corr:
            faab_vs_standings[str(yr)] = year_corr

    return {
        "years": years,
        "teams": dict(all_teams),
        "yearly_summary": yearly_summary,
        "faab_vs_standings": faab_vs_standings,
    }


# ------------------------------------------------------------------
# #6: Position preference analysis (draft $20+ non-keeper picks)
# ------------------------------------------------------------------

def compute_position_preference(years: list[int] | None = None, min_cost: int = 20) -> dict:
    """Analyze draft position preferences by team.

    Looks at picks costing >= min_cost. Position data comes from the draft
    data file if available (player_position field), otherwise from contracts.

    Returns:
        {
            "years": [...],
            "min_cost": 20,
            "teams": {
                "manager_name": {
                    "yearly": {
                        "2025": {
                            "picks": [
                                {"player": "...", "position": "OF", "cost": 45},
                            ],
                            "position_breakdown": {"OF": 3, "SP": 2, ...},
                            "total_picks": 5, "total_spent": 180,
                        },
                    },
                    "career_position_breakdown": {"OF": 8, "SP": 6, ...},
                }
            },
            "league_position_breakdown": {"OF": 40, "SP": 30, ...},
        }
    """
    if years is None:
        years = _available_years()

    # Build position lookup from contracts/DB for fallback
    pos_lookup = _build_position_lookup()

    # Load keeper data to exclude keeper players
    hist = _load_historical_keepers()

    all_teams: dict[str, dict] = defaultdict(lambda: {"yearly": {}, "career_pos": defaultdict(int)})
    league_pos: dict[str, int] = defaultdict(int)

    for year in years:
        draft = _load_draft(year)
        if not draft:
            continue

        year_str = str(year)

        # Build keeper set (historical_keepers + contracts JSON)
        keeper_normalized = _build_keeper_set(year, hist)

        for pick in draft:
            cost = pick.get("cost", 0)
            if cost < min_cost:
                continue

            mgr = pick.get("manager", "Unknown")
            player = pick.get("player_name", "")

            # Skip keeper players - only analyze actual draft picks
            if _normalize_player_name(player) in keeper_normalized:
                continue
            # Use draft data position first, then fallback to lookup
            position = pick.get("player_position", "") or pos_lookup.get(player, "")

            # Normalize position to primary category
            pos_cat = _categorize_position(position)

            if year_str not in all_teams[mgr]["yearly"]:
                all_teams[mgr]["yearly"][year_str] = {
                    "picks": [], "position_breakdown": defaultdict(int),
                    "total_picks": 0, "total_spent": 0,
                }

            yd = all_teams[mgr]["yearly"][year_str]
            yd["picks"].append({"player": player, "position": position, "pos_category": pos_cat, "cost": cost})
            yd["position_breakdown"][pos_cat] += 1
            yd["total_picks"] += 1
            yd["total_spent"] += cost

            all_teams[mgr]["career_pos"][pos_cat] += 1
            league_pos[pos_cat] += 1

    # Convert defaultdicts to regular dicts for JSON serialization
    result_teams = {}
    for mgr, data in all_teams.items():
        yearly = {}
        for yr, yd in data["yearly"].items():
            yearly[yr] = {
                "picks": yd["picks"],
                "position_breakdown": dict(yd["position_breakdown"]),
                "total_picks": yd["total_picks"],
                "total_spent": yd["total_spent"],
            }
        result_teams[mgr] = {
            "yearly": yearly,
            "career_position_breakdown": dict(data["career_pos"]),
        }

    return {
        "years": years,
        "min_cost": min_cost,
        "teams": result_teams,
        "league_position_breakdown": dict(league_pos),
    }


# ------------------------------------------------------------------
# Trade activity analytics
# ------------------------------------------------------------------

def compute_trade_stats(years: list[int] | None = None) -> dict:
    """Compute per-team trade activity across years.

    Each trade involves 2 teams. Both teams get credited with 1 trade.
    Also lists which players were exchanged.

    Returns:
        {
            "years": [2025, ...],
            "teams": {
                "manager_name": {
                    "yearly": {
                        "2025": {
                            "trade_count": 3,
                            "players_received": ["Player A", ...],
                            "players_sent": ["Player B", ...],
                            "trades": [
                                {"partner": "Other GM", "received": [...], "sent": [...],
                                 "timestamp": "..."},
                            ],
                        },
                    },
                }
            },
            "yearly_summary": {
                "2025": {"total_trades": 9, "team_count": 16}
            }
        }
    """
    if years is None:
        years = _available_years()

    all_teams: dict[str, dict] = defaultdict(lambda: {"yearly": {}})
    yearly_summary: dict[str, dict] = {}

    for year in years:
        txs = _load_transactions(year)
        draft = _load_draft(year)

        year_str = str(year)

        # Map team_key -> manager name using draft data
        key_to_mgr: dict[str, str] = {}
        for pick in draft:
            tk = pick.get("team_key", "")
            mgr = pick.get("manager", "")
            if tk and mgr:
                key_to_mgr[tk] = mgr

        # Also map team_name -> manager (fallback)
        name_to_mgr: dict[str, str] = {}
        for pick in draft:
            tn = pick.get("team_name", "")
            mgr = pick.get("manager", "")
            if tn and mgr:
                name_to_mgr[tn] = mgr

        trade_txs = [tx for tx in txs if tx.get("type") == "trade"]

        # Track per-team trades
        team_trades: dict[str, dict] = defaultdict(
            lambda: {"trade_count": 0, "players_received": [], "players_sent": [], "trades": []}
        )

        for tx in trade_txs:
            players = tx.get("players", [])
            ts = tx.get("timestamp", "")

            # Group players by direction: which teams sent/received
            # Each player moves from source_team -> destination_team
            # A trade has exactly 2 sides
            sides: dict[str, dict] = defaultdict(lambda: {"sent": [], "received": []})

            for p in players:
                src_key = p.get("source_team_key", "")
                dst_key = p.get("destination_team_key", "")
                pname = p.get("name", "")
                src_mgr = key_to_mgr.get(src_key, name_to_mgr.get(
                    p.get("source_team_name", ""), p.get("source_team_name", "Unknown")))
                dst_mgr = key_to_mgr.get(dst_key, name_to_mgr.get(
                    p.get("destination_team_name", ""), p.get("destination_team_name", "Unknown")))

                sides[src_mgr]["sent"].append(pname)
                sides[dst_mgr]["received"].append(pname)

            # For each team involved, record the trade
            mgr_list = list(sides.keys())
            for mgr in mgr_list:
                team_trades[mgr]["trade_count"] += 1
                team_trades[mgr]["players_received"].extend(sides[mgr]["received"])
                team_trades[mgr]["players_sent"].extend(sides[mgr]["sent"])

                # Find trade partner(s)
                partners = [m for m in mgr_list if m != mgr]
                partner_str = ", ".join(partners) if partners else "Unknown"
                team_trades[mgr]["trades"].append({
                    "partner": partner_str,
                    "received": sides[mgr]["received"],
                    "sent": sides[mgr]["sent"],
                    "timestamp": ts,
                })

        # Aggregate
        for mgr, td in team_trades.items():
            all_teams[mgr]["yearly"][year_str] = {
                "trade_count": td["trade_count"],
                "players_received": td["players_received"],
                "players_sent": td["players_sent"],
                "trades": td["trades"],
            }

        yearly_summary[year_str] = {
            "total_trades": len(trade_txs),
            "team_count": len(team_trades),
        }

    return {
        "years": years,
        "teams": dict(all_teams),
        "yearly_summary": yearly_summary,
    }


def _categorize_position(position: str) -> str:
    """Categorize Yahoo position string into detailed position.

    Yahoo positions: C, 1B, 2B, 3B, SS, LF, CF, RF, OF, SP, RP, DH, Util
    Returns the primary (first) position as-is for detailed breakdown.
    Normalizes OF -> OF, P -> RP, Util -> DH.
    """
    if not position:
        return "Unknown"

    # Take the first listed position
    primary = position.split(",")[0].strip()

    if primary in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "SP", "RP"):
        return primary
    if primary == "OF":
        return "OF"
    if primary == "P":
        return "RP"
    if primary in ("DH", "Util"):
        return "DH"
    return primary or "Unknown"


# ------------------------------------------------------------------
# Historical keeper / contract data loaders
# ------------------------------------------------------------------

def _load_historical_keepers() -> dict[str, dict[str, list[dict]]]:
    """Load historical keeper data from JSON (parsed from Excel).

    Returns: {"2023": {"Manager": [{"player":..., "salary":..., "contract_type":...}]}}
    """
    path = DATA_DIR / "historical_keepers.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Remove metadata key
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _load_2026_contracts() -> dict[str, list[dict]]:
    """Load 2026 contracts grouped by manager.

    Returns: {"Manager": [{"player":..., "salary":..., "contract_type":..., "source":...}]}
    """
    path = DATA_DIR / "2026_contracts_v2.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        contracts = json.load(f)

    result: dict[str, list[dict]] = {}
    for team_name, team_data in contracts.get("teams", {}).items():
        mgr = team_data.get("manager", team_name)
        players = []
        for p in team_data.get("players", []):
            # contract_type is just "N" for N-contracts; extract actual N number
            # from contract_2026 field (format: "N2/$21" or "O/$20")
            raw_ct = p.get("contract_type", "")
            c2026 = p.get("contract_2026", "")
            contract_type = raw_ct
            if raw_ct == "N" and c2026:
                m = re.match(r"(N\d+|O)/", c2026)
                if m:
                    contract_type = m.group(1)

            players.append({
                "player": p.get("name", ""),
                "salary": p.get("salary", 0),
                "contract_type": contract_type,
                "contract_2025": p.get("contract_2025", ""),
                "contract_2026": c2026,
                "source": p.get("source", ""),
                "position": p.get("position", ""),
            })
        result[mgr] = players
    return result


def _resolve_manager_name(name: str) -> str:
    """Resolve manager succession (e.g. hyc莊翔宇 -> Hank)."""
    return _MGR_SUCCESSION.get(name, name)


def _build_keeper_set(year: int, hist: dict) -> set[str]:
    """Build normalized keeper name set for a given draft year.

    Uses historical_keepers.json for 2023-2025 and 2026_contracts_v2.json
    for 2026+. Players in this set should be excluded from draft stats.
    """
    keeper_norm: set[str] = set()
    year_str = str(year)
    prev_year_str = str(year - 1)

    # Method 1: Previous year roster from historical_keepers.json
    if prev_year_str in hist:
        for _mgr, players in hist[prev_year_str].items():
            for p in players:
                keeper_norm.add(_normalize_player_name(p["player"]))

    # Method 2: Current year non-A contracts from historical_keepers.json
    if year_str in hist:
        for _mgr, players in hist[year_str].items():
            for p in players:
                ct = p.get("contract_type", "A")
                if ct != "A":
                    keeper_norm.add(_normalize_player_name(p["player"]))

    # Method 3: For 2026+, use contracts JSON (all players = keepers from prev year)
    contracts_path = DATA_DIR / f"{year}_contracts_v2.json"
    if contracts_path.exists():
        with open(contracts_path, encoding="utf-8") as f:
            contracts_data = json.load(f)
        for _team_name, team_data in contracts_data.get("teams", {}).items():
            for p in team_data.get("players", []):
                keeper_norm.add(_normalize_player_name(p.get("name", "")))

    return keeper_norm


# ------------------------------------------------------------------
# Salary Rankings (per year, keepers + draft picks)
# ------------------------------------------------------------------

def compute_salary_rankings(years: list[int] | None = None) -> dict:
    """Compute per-year salary rankings (Top 20).

    Data sources:
      - 2023-2025: historical_keepers.json (keepers only, no draft data for 2023-2024)
      - 2025 also has yahoo_2025_draft.json (draft picks)
      - 2026: 2026_contracts_v2.json (all players)

    Returns:
        {
            "years": [2023, 2024, 2025, 2026],
            "rankings": {
                "2023": [
                    {"rank": 1, "player": "...", "salary": 60, "contract_type": "B",
                     "manager": "...", "source": "keeper", "position": ""},
                    ...
                ],
            }
        }
    """
    hist = _load_historical_keepers()

    # Only show completed seasons (2026 draft not yet done)
    available = sorted(set(int(y) for y in hist.keys()))

    if years:
        available = [y for y in available if y in years]

    rankings: dict[str, list[dict]] = {}

    for year in available:
        all_players: list[dict] = []
        year_str = str(year)

        if year <= 2025 and year_str in hist:
            # Keeper data from Excel
            for mgr, players in hist[year_str].items():
                resolved_mgr = _resolve_manager_name(mgr)
                for p in players:
                    all_players.append({
                        "player": p["player"],
                        "salary": p["salary"],
                        "contract_type": p["contract_type"],
                        "manager": resolved_mgr,
                        "source": "keeper",
                        "position": p.get("position", ""),
                    })

            # Add draft picks for years that have Yahoo draft data
            draft = _load_draft(year)
            if draft:
                for pick in draft:
                    all_players.append({
                        "player": pick.get("player_name", ""),
                        "salary": pick.get("cost", 0),
                        "contract_type": "A",
                        "manager": pick.get("manager", "Unknown"),
                        "source": "draft",
                        "position": pick.get("player_position", ""),
                    })

        # Deduplicate: if same player appears as both keeper and draft,
        # keep the one with the more advanced contract (keeper > draft)
        # Contract priority: N > O > B > A > R > FA
        _ct_priority = {"FA": 0, "R": 1, "A": 2, "B": 3, "O": 4}
        def _contract_rank(ct: str) -> int:
            if ct.startswith("N"):
                return 5 + int(ct[1:]) if len(ct) > 1 and ct[1:].isdigit() else 5
            return _ct_priority.get(ct, 2)

        seen: dict[str, dict] = {}
        for p in all_players:
            name = p["player"]
            if name not in seen or _contract_rank(p["contract_type"]) > _contract_rank(seen[name]["contract_type"]):
                seen[name] = p
        unique_players = list(seen.values())

        # Compute per-manager total salary for % calculation
        mgr_totals: dict[str, int] = defaultdict(int)
        for p in unique_players:
            mgr_totals[p["manager"]] += p["salary"]

        # Sort by salary descending, take top 20
        unique_players.sort(key=lambda x: (-x["salary"], x["player"]))
        top20 = unique_players[:20]
        # Salary cap: $300 + (year - 2024 + 1) * $5 for 2024+, else $300
        salary_cap = 300 + (year - 2024 + 1) * 5 if year >= 2024 else 300
        for i, p in enumerate(top20, 1):
            p["rank"] = i
            p["salary_pct"] = round(p["salary"] / salary_cap * 100, 1)

        rankings[year_str] = top20

    return {
        "years": available,
        "rankings": rankings,
    }


# ------------------------------------------------------------------
# Contract Total Value Rankings (N-contract tracking)
# ------------------------------------------------------------------

def compute_contract_values() -> dict:
    """Compute total contract value for all N-extension contracts.

    Traces N-contract players across 2023-2026 to find the original N value,
    then calculates: total_value = salary * (N_original + 2)
    where +2 accounts for the B year and O year.

    Returns:
        {
            "contracts": [
                {
                    "player": "Vladimir Guerrero Jr.",
                    "salary": 51,
                    "original_n": 9,
                    "total_years": 11,
                    "total_value": 561,
                    "first_seen_year": 2023,
                    "first_seen_contract": "N9",
                    "current_contract": "N6",
                    "current_year": 2026,
                    "manager": "Hank",
                    "manager_history": ["hyc莊翔宇 (2023)", "Hank (2025)"],
                    "years_remaining": 7,
                },
                ...
            ]
        }
    """
    hist = _load_historical_keepers()
    contracts_2026 = _load_2026_contracts()

    # Build a map of player -> [{year, salary, contract_type, manager}]
    player_history: dict[str, list[dict]] = defaultdict(list)

    # 2023-2025 from historical keepers
    for year_str, mgr_data in hist.items():
        year = int(year_str)
        for mgr, players in mgr_data.items():
            for p in players:
                ct = p["contract_type"]
                if ct.startswith("N"):
                    player_history[p["player"]].append({
                        "year": year,
                        "salary": p["salary"],
                        "contract_type": ct,
                        "manager": mgr,
                    })

    # 2026 from contracts
    for mgr, players in contracts_2026.items():
        for p in players:
            ct = p["contract_type"]
            if ct.startswith("N"):
                player_history[p["player"]].append({
                    "year": 2026,
                    "salary": p["salary"],
                    "contract_type": ct,
                    "manager": mgr,
                })
            # Also check contract_2025 field (format: "$51/N7")
            c2025 = p.get("contract_2025", "")
            if c2025:
                m = re.match(r"\$?(\d+)/(N\d+)", c2025.replace("$", ""))
                if m:
                    sal = int(m.group(1))
                    ct25 = m.group(2)
                    # Only add if we don't already have 2025 data from hist
                    existing_years = [h["year"] for h in player_history.get(p["player"], [])]
                    if 2025 not in existing_years:
                        player_history[p["player"]].append({
                            "year": 2025,
                            "salary": sal,
                            "contract_type": ct25,
                            "manager": mgr,
                        })

    # Process each player to find original N and compute total value
    contracts: list[dict] = []

    for player_name, history in player_history.items():
        if not history:
            continue

        # Sort by year
        history.sort(key=lambda x: x["year"])

        # Find the highest N value (earliest/original extension)
        max_n = 0
        first_entry = history[0]
        current_entry = history[-1]

        for h in history:
            ct = h["contract_type"]
            n_val = int(ct[1:]) if ct[1:].isdigit() else 0
            if n_val > max_n:
                max_n = n_val
                first_entry = h

        # Total years = B(1) + N(original) + O(1) = original_N + 2
        total_years = max_n + 2
        salary = first_entry["salary"]
        total_value = salary * total_years

        # Current N remaining
        current_ct = current_entry["contract_type"]
        current_n = int(current_ct[1:]) if current_ct[1:].isdigit() else 0
        years_remaining = current_n + 1  # N remaining + O year

        # Manager history
        mgr_history = []
        seen_mgrs = set()
        for h in history:
            resolved = _resolve_manager_name(h["manager"])
            if resolved not in seen_mgrs:
                seen_mgrs.add(resolved)
                mgr_history.append(f"{resolved} ({h['year']})")

        contracts.append({
            "player": player_name,
            "salary": salary,
            "original_n": max_n,
            "total_years": total_years,
            "total_value": total_value,
            "first_seen_year": first_entry["year"],
            "first_seen_contract": first_entry["contract_type"],
            "current_contract": current_ct,
            "current_year": current_entry["year"],
            "manager": _resolve_manager_name(current_entry["manager"]),
            "manager_history": mgr_history,
            "years_remaining": years_remaining,
        })

    # Exclude players with legal issues (frozen contracts, not paying salary)
    _excluded_players = {"Wander Franco"}
    contracts = [c for c in contracts if c["player"] not in _excluded_players]

    # Sort by total_value descending
    contracts.sort(key=lambda x: (-x["total_value"], x["player"]))

    return {"contracts": contracts}


# ------------------------------------------------------------------
# League Summary / Overview
# ------------------------------------------------------------------

def compute_league_summary() -> dict:
    """Compute league-wide summary stats combining all analytics.

    Returns highlights and key stats across all categories for the overview tab.
    """
    hist = _load_historical_keepers()
    contracts_2026 = _load_2026_contracts()
    available_years = _available_years()

    summary: dict = {
        "keeper_stats": {},
        "draft_highlights": {},
        "contract_highlights": {},
        "trade_highlights": {},
    }

    # --- Keeper stats per year ---
    for year_str, mgr_data in hist.items():
        year_players = []
        for mgr, players in mgr_data.items():
            resolved = _resolve_manager_name(mgr)
            total_cost = sum(p["salary"] for p in players)
            year_players.append({
                "manager": resolved,
                "keeper_count": len(players),
                "total_cost": total_cost,
                "avg_cost": round(total_cost / len(players), 1) if players else 0,
            })
        year_players.sort(key=lambda x: -x["total_cost"])
        summary["keeper_stats"][year_str] = {
            "teams": year_players,
            "league_avg_cost": round(
                sum(t["total_cost"] for t in year_players) / len(year_players), 1
            ) if year_players else 0,
            "highest_spender": year_players[0] if year_players else None,
            "lowest_spender": year_players[-1] if year_players else None,
        }

    # --- Draft highlights (from yahoo data) ---
    for year in available_years:
        draft = _load_draft(year)
        if not draft:
            continue
        year_str = str(year)
        costs = [p.get("cost", 0) for p in draft]
        managers_cost: dict[str, int] = defaultdict(int)
        for p in draft:
            managers_cost[p.get("manager", "Unknown")] += p.get("cost", 0)

        top_mgr = max(managers_cost.items(), key=lambda x: x[1]) if managers_cost else ("", 0)
        sorted_costs = sorted(costs, reverse=True)
        top10_costs = sorted_costs[:10]
        summary["draft_highlights"][year_str] = {
            "total_picks": len(draft),
            "total_spent": sum(costs),
            "avg_pick_cost": round(sum(costs) / len(costs), 1) if costs else 0,
            "max_pick": max(costs) if costs else 0,
            "top10_avg": round(sum(top10_costs) / len(top10_costs), 1) if top10_costs else 0,
            "biggest_spender": {"manager": top_mgr[0], "total": top_mgr[1]},
        }

    # --- Contract highlights (top 5 all-time) ---
    cv = compute_contract_values()
    summary["contract_highlights"] = {
        "top5": cv["contracts"][:5],
        "total_n_contracts": len(cv["contracts"]),
        "total_committed_value": sum(c["total_value"] for c in cv["contracts"]),
    }

    # --- Trade highlights ---
    for year in available_years:
        txs = _load_transactions(year)
        trade_count = len([tx for tx in txs if tx.get("type") == "trade"])
        faab_count = len([tx for tx in txs if tx.get("faab_bid") and tx["faab_bid"] > 0])
        year_str = str(year)
        summary["trade_highlights"][year_str] = {
            "trade_count": trade_count,
            "faab_transactions": faab_count,
            "total_transactions": len(txs),
        }

    return summary
