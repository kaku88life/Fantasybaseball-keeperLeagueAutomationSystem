"""
Draft and FAAB analytics.

Reads data/yahoo_{year}_draft.json and data/yahoo_{year}_transactions.json
to compute per-team, per-year statistics for the frontend analytics page.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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
    lookup: dict[str, str] = {}

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

    # Source 2: players DB table (has yahoo position data)
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

    for year in years:
        draft = _load_draft(year)
        if not draft:
            continue

        year_str = str(year)
        team_picks: dict[str, list[dict]] = defaultdict(list)

        league_max = {"cost": 0, "player": "", "manager": ""}

        for pick in draft:
            mgr = pick.get("manager", "Unknown")
            cost = pick.get("cost", 0)
            player = pick.get("player_name", "")
            position = pick.get("player_position", "") or pos_lookup.get(player, "")

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
        faab_budget = meta.get("faab_budget", 100)  # default $100

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

    return {
        "years": years,
        "teams": dict(all_teams),
        "yearly_summary": yearly_summary,
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

    all_teams: dict[str, dict] = defaultdict(lambda: {"yearly": {}, "career_pos": defaultdict(int)})
    league_pos: dict[str, int] = defaultdict(int)

    for year in years:
        draft = _load_draft(year)
        if not draft:
            continue

        year_str = str(year)

        for pick in draft:
            cost = pick.get("cost", 0)
            if cost < min_cost:
                continue

            mgr = pick.get("manager", "Unknown")
            player = pick.get("player_name", "")
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
    """Categorize Yahoo position string into broad category.

    Yahoo positions: C, 1B, 2B, 3B, SS, LF, CF, RF, OF, SP, RP, DH, Util
    Categories: C, IF (1B/2B/3B/SS), OF (LF/CF/RF/OF), SP, RP, DH/Util, Unknown
    """
    if not position:
        return "Unknown"

    # Take the first listed position
    primary = position.split(",")[0].strip()

    if primary in ("C",):
        return "C"
    if primary in ("1B", "2B", "3B", "SS"):
        return "IF"
    if primary in ("LF", "CF", "RF", "OF"):
        return "OF"
    if primary in ("SP",):
        return "SP"
    if primary in ("RP",):
        return "RP"
    if primary in ("DH", "Util"):
        return "DH"
    return primary or "Unknown"
