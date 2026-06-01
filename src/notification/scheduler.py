"""
APScheduler-based background scheduler.

Jobs:
1. Keeper reminder: optional LINE group reminders every N days during keeper period.
2. Rookie call-up monitor: optional daily check for R-contract player MLB debuts.
3. Daily AR-Rank + season stats refresh: single-pass at 18:00 during MLB season.
4. Daily player status update: IL/DTD/NA/O status during MLB season; LINE digest optional.
5. Daily transaction fetch: Yahoo transactions during MLB season.
6. Daily roster + snapshot rebuild (with owner_manager sync): 00:30 Taiwan time.
7. Weekly war report: Monday 21:00 during MLB season.
8. Monthly war report + rookie watch: 1st of each month 20:45 during MLB season.

Yearly auto-mode: set REMINDER_MONTH / REMINDER_START_DAY / REMINDER_END_DAY
to define a fixed annual window (e.g. March 1-15 every year).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- New: fixed annual window (preferred) ---
REMINDER_MONTH = int(os.getenv("REMINDER_MONTH", "3"))          # default March
REMINDER_START_DAY = int(os.getenv("REMINDER_START_DAY", "1"))   # default 1st
REMINDER_END_DAY = int(os.getenv("REMINDER_END_DAY", "15"))      # default 15th

# --- Legacy: explicit date range (overrides annual window if set) ---
KEEPER_REMINDER_START = os.getenv("KEEPER_REMINDER_START", "")
KEEPER_REMINDER_END = os.getenv("KEEPER_REMINDER_END", "")

REMINDER_CRON_HOUR = int(os.getenv("REMINDER_CRON_HOUR", "12"))
REMINDER_CRON_TZ = os.getenv("REMINDER_CRON_TZ", "Asia/Taipei")
REMINDER_INTERVAL_DAYS = int(os.getenv("REMINDER_INTERVAL_DAYS", "3"))
KEEPER_REMINDER_ENABLED = _env_flag("KEEPER_REMINDER_ENABLED", "false")

# --- Rookie call-up monitoring ---
# Immediate call-up LINE pushes are off by default; monthly rookie watch covers
# the group-facing summary without burning quota on each small event.
ROOKIE_MONITOR_ENABLED = _env_flag("ROOKIE_MONITOR_ENABLED", "false")
ROOKIE_MONITOR_START_MONTH = int(os.getenv("ROOKIE_MONITOR_START_MONTH", "3"))
ROOKIE_MONITOR_END_MONTH = int(os.getenv("ROOKIE_MONITOR_END_MONTH", "9"))
ROOKIE_WATCH_R_LIMIT = int(os.getenv("ROOKIE_WATCH_R_LIMIT", "3"))
ROOKIE_WATCH_FA_LIMIT = int(os.getenv("ROOKIE_WATCH_FA_LIMIT", "5"))
ROOKIE_WATCH_STATS_ENABLED = _env_flag("ROOKIE_WATCH_STATS_ENABLED", "true")
ROOKIE_WATCH_STATS_LIMIT = int(os.getenv("ROOKIE_WATCH_STATS_LIMIT", "8"))
ROOKIE_WATCH_STATS_TIMEOUT_SECONDS = float(
    os.getenv("ROOKIE_WATCH_STATS_TIMEOUT_SECONDS", "25")
)

# --- Daily roster sync ---
DAILY_SYNC_HOUR = int(os.getenv("DAILY_SYNC_HOUR", "0"))           # midnight Taiwan time

# --- Injury notification batching ---
# Batch every N days so we don't spam LINE daily with tiny status changes.
INJURY_BATCH_DAYS = int(os.getenv("INJURY_BATCH_DAYS", "3"))
INJURY_LINE_ENABLED = _env_flag("INJURY_LINE_ENABLED", "false")
PROSPECT_UPDATE_LINE_ENABLED = _env_flag("PROSPECT_UPDATE_LINE_ENABLED", "false")

_scheduler = None
MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"
_MLB_PERSON_CACHE: dict[str, dict | None] = {}
_ROOKIE_MONTH_STATS_CACHE: dict[tuple[str, str, int, int], str] = {}


# --- MLB team abbreviation mapping for war report matchup display ---
# Keywords (lowercase) -> 3-letter MLB abbreviation. Fuzzy substring match,
# longer keywords tried first to avoid false matches (e.g. "white sox" before "sox").
_MLB_TEAM_ABBR_KEYWORDS: list[tuple[str, str]] = [
    ("diamondbacks", "ARI"), ("d-backs", "ARI"), ("dbacks", "ARI"), ("arizona", "ARI"),
    ("braves", "ATL"), ("atlanta", "ATL"),
    ("orioles", "BAL"), ("baltimore", "BAL"),
    ("red sox", "BOS"), ("boston", "BOS"),
    ("white sox", "CWS"),
    ("cubs", "CHC"),
    ("reds", "CIN"), ("cincinnati", "CIN"),
    ("guardians", "CLE"), ("indians", "CLE"), ("cleveland", "CLE"),
    ("rockies", "COL"), ("colorado", "COL"),
    ("tigers", "DET"), ("detroit", "DET"),
    ("astros", "HOU"), ("houston", "HOU"),
    ("royals", "KC"), ("kansas city", "KC"),
    ("angels", "LAA"),
    ("dodgers", "LAD"), ("dodge", "LAD"),
    ("marlins", "MIA"), ("miami", "MIA"),
    ("brewers", "MIL"), ("milwaukee", "MIL"),
    ("twins", "MIN"), ("minnesota", "MIN"),
    ("yankees", "NYY"),
    ("mets", "NYM"),
    ("athletics", "OAK"), ("oakland", "OAK"),
    ("phillies", "PHI"), ("philadelphia", "PHI"),
    ("pirates", "PIT"), ("pittsburgh", "PIT"),
    ("padres", "SD"), ("san diego", "SD"),
    ("mariners", "SEA"), ("seattle", "SEA"),
    ("giants", "SF"), ("san francisco", "SF"),
    ("cardinals", "STL"), ("st. louis", "STL"), ("st louis", "STL"),
    ("rays", "TB"), ("tampa bay", "TB"), ("tampa", "TB"),
    ("rangers", "TEX"), ("texas", "TEX"),
    ("blue jays", "TOR"), ("jays", "TOR"), ("toronto", "TOR"),
    ("nationals", "WSH"), ("washington", "WSH"),
]
# Pre-sort by keyword length descending so longer/more specific matches win.
_MLB_TEAM_ABBR_KEYWORDS.sort(key=lambda x: -len(x[0]))


def _fantasy_team_to_mlb_abbr(team_name: str) -> str:
    """Return 3-letter MLB abbrev matched from a fantasy team name, or "" if no match."""
    if not team_name:
        return ""
    name_lower = team_name.lower()
    for kw, abbr in _MLB_TEAM_ABBR_KEYWORDS:
        if kw in name_lower:
            return abbr
    return ""


# --- Yahoo stat_id -> display name (MLB standard) ---
# Used to parse player_stats in war report top batter/pitcher sections.
# IDs verified against Yahoo Fantasy MLB public docs; may need adjustment
# if league custom stats diverge (debug log in scheduler dumps first player's
# raw stats to help verify).
_YAHOO_STAT_ID_NAME: dict[str, str] = {
    # Batting
    "3": "AVG",
    "6": "AB",
    "7": "R",
    "8": "H",
    "12": "HR",
    "13": "RBI",
    "16": "SB",
    "55": "OPS",
    # Pitching
    "50": "IP",
    "26": "ERA",
    "27": "WHIP",
    "28": "W",
    "32": "SV",
    "42": "K",
    "57": "HLD",
    "83": "QS",
}


# --- Shared formatting helpers for LINE reports (weekly / monthly war reports) ---

def _visual_width(s: str) -> int:
    """Rough visual width: CJK/fullwidth chars ≈ 2 cells, ASCII ≈ 1."""
    w = 0
    for c in s:
        o = ord(c)
        if (
            0x1100 <= o <= 0x115F
            or 0x2600 <= o <= 0x26FF
            or 0x2700 <= o <= 0x27BF
            or 0x2B00 <= o <= 0x2BFF
            or 0x2E80 <= o <= 0x303E
            or 0x3041 <= o <= 0x33FF
            or 0x3400 <= o <= 0x4DBF
            or 0x4E00 <= o <= 0x9FFF
            or 0xA000 <= o <= 0xA4CF
            or 0xAC00 <= o <= 0xD7A3
            or 0xF900 <= o <= 0xFAFF
            or 0xFE30 <= o <= 0xFE4F
            or 0xFF00 <= o <= 0xFF60
            or 0xFFE0 <= o <= 0xFFE6
            or 0x1F300 <= o <= 0x1FAFF
        ):
            w += 2
        else:
            w += 1
    return w


def _center_line(text: str, width: int) -> str:
    """Center `text` within a `width`-cell row using fullwidth spaces for bulk padding.
    LINE's desktop proportional font collapses leading ASCII spaces, so we bias toward
    fullwidth (\u3000) padding which takes 2 cells and renders reliably.
    """
    pad_cells = max(0, (width - _visual_width(text)) // 2)
    fw = "\u3000" * (pad_cells // 2)
    sp = " " * (pad_cells % 2)
    return fw + sp + text


def _pad_right_visual(s: str, width: int) -> str:
    return s + " " * max(0, width - _visual_width(s))


def _team_mgr_block(team_name: str, manager_name: str) -> str:
    """Format `ABBR (manager)` or fall back to raw team name / ? when abbr lookup fails."""
    abbr = _fantasy_team_to_mlb_abbr(team_name or "") or team_name or "?"
    mgr = manager_name or "?"
    return f"{abbr}  ({mgr})"


def _format_owner_label(info: dict[str, Any]) -> str:
    """Prefer the Yahoo fantasy team name, with manager as a disambiguator."""
    manager = (info.get("owner_manager") or "").strip()
    team_name = (info.get("owner_team_name") or "").strip()
    if team_name and manager and team_name != manager:
        return f"{team_name}（{manager}）"
    return team_name or manager or "FA"


def _format_player_meta(position: str, mlb_team: str) -> str:
    return "/".join(part for part in (position, mlb_team) if part)


def _normalize_player_name(name: str) -> str:
    """Normalize names for cross-source matching."""
    import unicodedata

    cleaned = (name or "").split("(")[0].strip()
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower().strip()
    for suffix in (" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return cleaned.replace(".", "").replace("-", " ")


def _format_stats_unavailable(label: str) -> list[str]:
    return [f"  Yahoo 暫未回傳{label}資料；請稍後再試。"]


def _load_top_prospects(data_dir) -> tuple[list[dict], dict[str, Any]]:
    """Load the checked-in top prospect candidate list."""
    import json

    path = data_dir / "top_100_prospects.json"
    debug: dict[str, Any] = {"path": str(path), "count": 0, "source": ""}
    if not path.exists():
        debug["error"] = "top_100_prospects.json not found"
        return [], debug
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prospects = data.get("prospects", [])
        debug.update({
            "count": len(prospects),
            "source": data.get("source", ""),
            "updated_at": data.get("updated_at", ""),
        })
        return prospects, debug
    except Exception as e:
        debug["error"] = str(e)
        return [], debug


def _build_current_owner_lookup(year: int) -> tuple[dict[str, dict], dict[str, Any]]:
    """Build player-name ownership from DB synced Yahoo rosters, with snapshot fallback."""
    debug: dict[str, Any] = {
        "synced_roster_players": 0,
        "snapshot_players": 0,
        "source": [],
    }
    owner_by_name: dict[str, dict] = {}

    try:
        from api.database import get_snapshot
        from api.serializers import dict_to_league_state

        snapshot = get_snapshot(year)
        if snapshot and snapshot.get("data"):
            league_state = dict_to_league_state(snapshot["data"])
            for team in league_state.teams:
                for player in team.players:
                    key = _normalize_player_name(player.name)
                    if not key:
                        continue
                    owner_by_name[key] = {
                        "owner_manager": team.manager_name,
                        "owner_team_name": team.team_name,
                        "position": player.position,
                        "mlb_team": player.mlb_team,
                        "contract_type": player.contract.contract_type.value,
                        "contract_display": player.contract.display,
                        "player_key": player.yahoo_player_id or "",
                    }
                    debug["snapshot_players"] += 1
            if debug["snapshot_players"]:
                debug["source"].append("league_snapshot")
    except Exception as e:
        debug["snapshot_error"] = str(e)

    try:
        from api.database import get_synced_roster

        rosters = get_synced_roster(year) or {}
        if isinstance(rosters, dict):
            for team_data in rosters.values():
                if not isinstance(team_data, dict):
                    continue
                manager = str(team_data.get("manager") or "").strip()
                team_name = str(team_data.get("team_name") or "").strip()
                for player in team_data.get("players", []):
                    if not isinstance(player, dict):
                        continue
                    key = _normalize_player_name(player.get("name", ""))
                    if not key:
                        continue
                    owner_by_name[key] = {
                        "owner_manager": manager,
                        "owner_team_name": team_name,
                        "position": player.get("position", ""),
                        "mlb_team": player.get("team", ""),
                        "contract_type": "",
                        "contract_display": "",
                        "player_key": player.get("player_key", ""),
                    }
                    debug["synced_roster_players"] += 1
            if debug["synced_roster_players"]:
                debug["source"].append("synced_rosters")
    except Exception as e:
        debug["synced_roster_error"] = str(e)

    return owner_by_name, debug


def _is_pitcher_position(position: str) -> bool:
    tokens = {
        p.strip().upper()
        for p in (position or "").replace("/", ",").split(",")
        if p.strip()
    }
    return bool(tokens & {"P", "SP", "RP", "LHP", "RHP"})


def _ip_to_outs(value: Any) -> int:
    try:
        text = str(value or "0").strip()
        whole, _, frac = text.partition(".")
        outs = int(whole or 0) * 3
        if frac:
            outs += min(int(frac[0]), 2)
        return outs
    except (ValueError, TypeError):
        return 0


def _outs_to_ip(outs: int) -> str:
    whole, rem = divmod(max(outs, 0), 3)
    return f"{whole}.{rem}"


def _safe_stat_int(stats: dict, *keys: str) -> int:
    for key in keys:
        value = stats.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (ValueError, TypeError):
                continue
    return 0


def _split_in_report_month(split: dict, year: int, report_month: int) -> bool:
    game = split.get("game") if isinstance(split.get("game"), dict) else {}
    raw_date = (
        split.get("date")
        or game.get("gameDate")
        or game.get("officialDate")
        or split.get("gameDate")
    )
    if not raw_date:
        return False
    try:
        dt = datetime.fromisoformat(str(raw_date)[:10])
        return dt.year == year and dt.month == report_month
    except ValueError:
        return False


def _http_timeout(deadline: float | None, default: float = 5.0) -> float:
    if deadline is None:
        return default
    import time as time_mod

    remaining = deadline - time_mod.monotonic()
    if remaining <= 0:
        return 0.0
    return max(0.5, min(default, remaining))


def _find_mlb_person(
    name: str,
    position: str,
    deadline: float | None = None,
) -> dict | None:
    import httpx

    clean_name = (name or "").split("(")[0].strip()
    cache_key = f"{clean_name.lower()}::{position}"
    if cache_key in _MLB_PERSON_CACHE:
        return _MLB_PERSON_CACHE[cache_key]

    try:
        timeout = _http_timeout(deadline)
        if timeout <= 0:
            return None
        resp = httpx.get(
            f"{MLB_STATS_API_BASE}/people/search",
            params={"names": clean_name, "hydrate": "currentTeam"},
            timeout=timeout,
        )
        resp.raise_for_status()
        rows = resp.json().get("people", [])
    except Exception:
        _MLB_PERSON_CACHE[cache_key] = None
        return None

    if not rows:
        _MLB_PERSON_CACHE[cache_key] = None
        return None

    best = rows[0]
    wants_pitcher = _is_pitcher_position(position)
    for row in rows:
        primary_pos = row.get("primaryPosition", {}).get("abbreviation", "")
        is_pitcher = primary_pos in {"P", "SP", "RP", "LHP", "RHP", "TWP"}
        if wants_pitcher == is_pitcher:
            best = row
            break

    _MLB_PERSON_CACHE[cache_key] = best
    return best


def _fetch_rookie_month_stats_line(
    name: str,
    position: str,
    year: int,
    report_month: int,
    month_label: str,
    deadline: float | None = None,
) -> str:
    """Return one compact MLB/MiLB monthly stat line for a prospect."""
    import httpx

    if not ROOKIE_WATCH_STATS_ENABLED:
        return ""

    cache_key = (name, position, year, report_month)
    if cache_key in _ROOKIE_MONTH_STATS_CACHE:
        return _ROOKIE_MONTH_STATS_CACHE[cache_key]

    person = _find_mlb_person(name, position, deadline)
    if not person:
        _ROOKIE_MONTH_STATS_CACHE[cache_key] = ""
        return ""

    mlb_id = person.get("id")
    if not mlb_id:
        _ROOKIE_MONTH_STATS_CACHE[cache_key] = ""
        return ""

    level_map = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "ROK"}
    level_order = ["MLB", "AAA", "AA", "A+", "A", "ROK"]
    prefers_pitching = _is_pitcher_position(position)
    hitting_by_level: dict[str, dict] = {}
    pitching_by_level: dict[str, dict] = {}
    seen_splits: set[tuple[str, str]] = set()

    for sport_id in level_map:
        timeout = _http_timeout(deadline)
        if timeout <= 0:
            break
        try:
            resp = httpx.get(
                f"{MLB_STATS_API_BASE}/people/{mlb_id}/stats",
                params={
                    "stats": "gameLog",
                    "group": "hitting,pitching",
                    "season": year,
                    "sportId": sport_id,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue

        for stat_group in data.get("stats", []):
            group_name = (
                stat_group.get("group", {}).get("displayName", "")
                or stat_group.get("group", {}).get("display_name", "")
            ).lower()
            for split in stat_group.get("splits", []):
                if not _split_in_report_month(split, year, report_month):
                    continue
                split_sport_id = (
                    split.get("sport", {}).get("id")
                    if isinstance(split.get("sport"), dict)
                    else None
                )
                level = level_map.get(split_sport_id or sport_id, "Other")
                game = split.get("game") if isinstance(split.get("game"), dict) else {}
                split_key = (
                    group_name,
                    str(
                        game.get("gamePk")
                        or split.get("date")
                        or game.get("gameDate")
                        or f"{level}:{len(seen_splits)}"
                    ),
                )
                if split_key in seen_splits:
                    continue
                seen_splits.add(split_key)
                stat = split.get("stat", {})
                if group_name == "hitting":
                    hitting = hitting_by_level.setdefault(
                        level,
                        {
                            "games": 0, "ab": 0, "h": 0, "hr": 0,
                            "rbi": 0, "r": 0, "sb": 0,
                        },
                    )
                    hitting["games"] += 1
                    hitting["ab"] += _safe_stat_int(stat, "atBats")
                    hitting["h"] += _safe_stat_int(stat, "hits")
                    hitting["hr"] += _safe_stat_int(stat, "homeRuns")
                    hitting["rbi"] += _safe_stat_int(stat, "rbi")
                    hitting["r"] += _safe_stat_int(stat, "runs")
                    hitting["sb"] += _safe_stat_int(stat, "stolenBases")
                elif group_name == "pitching":
                    pitching = pitching_by_level.setdefault(
                        level,
                        {
                            "games": 0, "outs": 0, "k": 0, "w": 0,
                            "sv": 0, "hld": 0, "er": 0, "h": 0, "bb": 0,
                        },
                    )
                    pitching["games"] += 1
                    pitching["outs"] += _ip_to_outs(stat.get("inningsPitched"))
                    pitching["k"] += _safe_stat_int(stat, "strikeOuts", "strikeouts")
                    pitching["w"] += _safe_stat_int(stat, "wins")
                    pitching["sv"] += _safe_stat_int(stat, "saves")
                    pitching["hld"] += _safe_stat_int(stat, "holds")
                    pitching["er"] += _safe_stat_int(stat, "earnedRuns")
                    pitching["h"] += _safe_stat_int(stat, "hits")
                    pitching["bb"] += _safe_stat_int(stat, "baseOnBalls", "walks")

    for level in level_order:
        hitting = hitting_by_level.get(
            level,
            {"games": 0, "ab": 0, "h": 0, "hr": 0, "rbi": 0, "r": 0, "sb": 0},
        )
        pitching = pitching_by_level.get(
            level,
            {
                "games": 0, "outs": 0, "k": 0, "w": 0,
                "sv": 0, "hld": 0, "er": 0, "h": 0, "bb": 0,
            },
        )
        has_hitting = hitting["games"] > 0 and (hitting["ab"] > 0 or hitting["h"] > 0)
        has_pitching = pitching["games"] > 0 and pitching["outs"] > 0

        if prefers_pitching and has_pitching:
            innings = pitching["outs"] / 3
            era = (pitching["er"] * 9 / innings) if innings else 0
            whip = ((pitching["h"] + pitching["bb"]) / innings) if innings else 0
            line = (
                f"{month_label} {level}: {_outs_to_ip(pitching['outs'])}IP "
                f"{pitching['k']}K {pitching['w']}W "
                f"{era:.2f}ERA {whip:.2f}WHIP"
            )
            _ROOKIE_MONTH_STATS_CACHE[cache_key] = line
            return line
        if (not prefers_pitching) and has_hitting:
            avg = hitting["h"] / hitting["ab"] if hitting["ab"] else 0
            line = (
                f"{month_label} {level}: {hitting['h']}-{hitting['ab']} "
                f"{_fmt_avg(str(round(avg, 3)))} "
                f"{hitting['hr']}HR {hitting['rbi']}RBI "
                f"{hitting['r']}R {hitting['sb']}SB"
            )
            _ROOKIE_MONTH_STATS_CACHE[cache_key] = line
            return line
        if has_pitching:
            innings = pitching["outs"] / 3
            era = (pitching["er"] * 9 / innings) if innings else 0
            whip = ((pitching["h"] + pitching["bb"]) / innings) if innings else 0
            line = (
                f"{month_label} {level}: {_outs_to_ip(pitching['outs'])}IP "
                f"{pitching['k']}K {era:.2f}ERA {whip:.2f}WHIP"
            )
            _ROOKIE_MONTH_STATS_CACHE[cache_key] = line
            return line

    _ROOKIE_MONTH_STATS_CACHE[cache_key] = ""
    return ""


def _build_rookie_watch_lines(
    year: int,
    report_month: int,
    month_label: str,
    data_dir,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Build monthly owned R-contract and unowned prospect watch sections."""
    debug: dict[str, Any] = {}
    prospects, prospect_debug = _load_top_prospects(data_dir)
    owner_by_name, owner_debug = _build_current_owner_lookup(year)
    debug["prospects"] = prospect_debug
    debug["ownership"] = owner_debug

    prospect_by_name = {
        _normalize_player_name(p.get("name", "")): p
        for p in prospects
        if _normalize_player_name(p.get("name", ""))
    }

    try:
        from src.notification.rookie_monitor import _load_r_contract_players

        r_players = _load_r_contract_players(year)
    except Exception as e:
        debug["r_error"] = str(e)
        r_players = []

    import time as time_mod

    stats_deadline = time_mod.monotonic() + ROOKIE_WATCH_STATS_TIMEOUT_SECONDS
    stats_remaining = ROOKIE_WATCH_STATS_LIMIT

    def maybe_stats_line(player_name: str, position: str) -> str:
        nonlocal stats_remaining
        if not ROOKIE_WATCH_STATS_ENABLED or stats_remaining <= 0:
            return ""
        if time_mod.monotonic() >= stats_deadline:
            return ""
        stats_remaining -= 1
        return _fetch_rookie_month_stats_line(
            player_name,
            position,
            year,
            report_month,
            month_label,
            stats_deadline,
        )

    r_candidates: list[dict] = []
    r_name_keys: set[str] = set()
    for rp in r_players:
        key = _normalize_player_name(rp.get("name", ""))
        if key:
            r_name_keys.add(key)
        prospect = prospect_by_name.get(key, {})
        rank = prospect.get("rank") or 9999
        r_candidates.append({**rp, "prospect": prospect, "rank": rank})
    r_candidates.sort(key=lambda p: (p.get("rank") or 9999, p.get("name", "")))
    debug["r_count"] = len(r_candidates)

    r_lines: list[str] = []
    if r_candidates:
        for idx, player in enumerate(r_candidates[:ROOKIE_WATCH_R_LIMIT], 1):
            prospect = player.get("prospect") or {}
            position = prospect.get("position") or player.get("position", "")
            mlb_team = prospect.get("mlb_team") or player.get("mlb_team", "")
            meta = _format_player_meta(position, mlb_team)
            label = f"{player['name']} ({meta})" if meta else player["name"]
            r_lines.append(f" {idx}. {label} - {_format_owner_label(player)}")
            tags = []
            if prospect.get("rank"):
                tags.append(f"Pipeline #{prospect['rank']}")
            if prospect.get("eta"):
                tags.append(f"ETA {prospect['eta']}")
            if tags:
                r_lines.append(f"    {' | '.join(tags)}")
            stats_line = maybe_stats_line(player["name"], position)
            r_lines.append(f"    {stats_line or f'{month_label} MLB/MiLB 數據暫缺'}")
    else:
        r_lines.append("  目前沒有可整理的 R 約新秀。")

    fa_lines: list[str] = []
    unowned: list[dict] = []
    if owner_by_name:
        for prospect in sorted(prospects, key=lambda p: p.get("rank") or 9999):
            key = _normalize_player_name(prospect.get("name", ""))
            if not key or key in r_name_keys or owner_by_name.get(key):
                continue
            unowned.append(prospect)
    debug["unowned_count"] = len(unowned)

    if unowned:
        for idx, prospect in enumerate(unowned[:ROOKIE_WATCH_FA_LIMIT], 1):
            position = prospect.get("position", "")
            mlb_team = prospect.get("mlb_team", "")
            meta = _format_player_meta(position, mlb_team)
            label = f"{prospect['name']} ({meta})" if meta else prospect["name"]
            fa_lines.append(f" {idx}. {label} - FA")
            tags = []
            if prospect.get("rank"):
                tags.append(f"Pipeline #{prospect['rank']}")
            if prospect.get("eta"):
                tags.append(f"ETA {prospect['eta']}")
            if prospect.get("age"):
                tags.append(f"{prospect['age']}歲")
            if tags:
                fa_lines.append(f"    {' | '.join(tags)}")
            stats_line = maybe_stats_line(prospect["name"], position)
            fa_lines.append(f"    {stats_line or f'{month_label} MLB/MiLB 數據暫缺'}")
    elif prospects and not owner_by_name:
        fa_lines.append("  ownership 資料暫缺，未持有名單先不列入月報。")
    else:
        fa_lines.append("  Top prospect 名單中沒有可列出的未持有新秀。")

    debug["stats_remaining"] = stats_remaining
    return r_lines, fa_lines, debug


def _walk_stats(obj, out: dict) -> None:
    """Recursively scan a Yahoo player payload for stat_id/value pairs.
    Yahoo wraps stats in varying depths depending on subresource ordering;
    this catches them regardless of which list-dict branch they live in.
    """
    if isinstance(obj, dict):
        if "stat_id" in obj and "value" in obj:
            sid = str(obj.get("stat_id", ""))
            if sid:
                out[sid] = str(obj.get("value", ""))
            return
        for v in obj.values():
            _walk_stats(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_stats(v, out)


def _safe_int(v, default: int = 0) -> int:
    """Convert Yahoo string/int fields to int with a safe fallback."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _walk_first(obj: Any, key: str) -> Any:
    """Return the first nested value for `key` in a Yahoo JSON payload."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _walk_first(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _walk_first(value, key)
            if found is not None:
                return found
    return None


def _parse_yahoo_top_player_entry(p_entry: list) -> dict:
    """Parse one Yahoo players collection entry for report top-player sections."""
    p_info: dict[str, Any] = {
        "name": "",
        "position": "",
        "mlb_team": "",
        "owner_team": "FA",
        "points": 0.0,
        "stats": {},
    }

    for item in (p_entry[0] if isinstance(p_entry[0], list) else [p_entry[0]]):
        if not isinstance(item, dict):
            continue
        if "name" in item:
            p_info["name"] = item["name"].get("full", "")
        if "display_position" in item:
            p_info["position"] = item["display_position"]
        if "editorial_team_abbr" in item:
            p_info["mlb_team"] = item["editorial_team_abbr"]

    ownership = _walk_first(p_entry, "ownership")
    if isinstance(ownership, dict):
        p_info["owner_team"] = ownership.get("owner_team_name", "FA")

    player_points = _walk_first(p_entry, "player_points")
    if isinstance(player_points, dict):
        try:
            p_info["points"] = float(player_points.get("total", 0))
        except (ValueError, TypeError):
            p_info["points"] = 0.0

    raw_stats: dict[str, str] = {}
    _walk_stats(p_entry, raw_stats)
    named_stats: dict[str, str] = {}
    for sid, name in _YAHOO_STAT_ID_NAME.items():
        if sid in raw_stats:
            named_stats[name] = raw_stats[sid]
    p_info["stats"] = named_stats
    p_info["_raw_stat_ids"] = list(raw_stats.keys())
    p_info["_raw_stats"] = raw_stats
    return p_info


def _fetch_yahoo_report_top_players(
    yahoo_api_get,
    league_key: str,
    *,
    sort_type: str,
    sort_week: int | None = None,
) -> tuple[list[dict], list[dict], str, dict[str, Any]]:
    """Fetch report top players, preferring Yahoo PTS and falling back to AR."""
    debug: dict[str, Any] = {}
    attempts: list[tuple[str, str]] = [("PTS", "Yahoo Fantasy Points（夢幻積分 PTS）")]
    if sort_type in {"lastweek", "lastmonth"}:
        attempts.append(("AR", "Yahoo Actual Rank（實際排名 AR）fallback"))

    for sort, source_label in attempts:
        suffix = f";sort={sort};sort_type={sort_type}"
        if sort_week is not None and sort_type == "week":
            suffix += f";sort_week={sort_week}"
        path = (
            f"/league/{league_key}/players"
            f"{suffix};count=50;out=stats,ownership"
        )
        try:
            pdata = yahoo_api_get(path)
            p_league = pdata.get("fantasy_content", {}).get("league", [])
            if len(p_league) < 2:
                debug[sort] = {
                    "path": path,
                    "error": f"p_league length {len(p_league)} < 2",
                    "raw_keys": list(pdata.get("fantasy_content", {}).keys()),
                }
                continue

            p_section = p_league[1].get("players", {})
            count_val = _safe_int(p_section.get("count", 0))
            if count_val == 0:
                debug[sort] = {
                    "path": path,
                    "error": "players count=0",
                    "p_section_keys": (
                        list(p_section.keys()) if isinstance(p_section, dict) else None
                    ),
                }
                continue

            batters: list[dict] = []
            pitchers: list[dict] = []
            first_sample: dict[str, Any] | None = None
            for pk_idx in range(count_val):
                p_entry = p_section.get(str(pk_idx), {}).get("player", [])
                if not p_entry or not isinstance(p_entry, list):
                    continue
                p_info = _parse_yahoo_top_player_entry(p_entry)
                if not p_info.get("name"):
                    continue
                if first_sample is None:
                    first_sample = {
                        "name": p_info.get("name"),
                        "position": p_info.get("position"),
                        "points": p_info.get("points"),
                        "raw_stat_ids": p_info.get("_raw_stat_ids"),
                        "named": p_info.get("stats"),
                    }
                if _is_pitcher_position(p_info.get("position", "")):
                    if len(pitchers) < 5:
                        pitchers.append(p_info)
                elif len(batters) < 5:
                    batters.append(p_info)
                if len(batters) >= 5 and len(pitchers) >= 5:
                    break

            debug[sort] = {
                "path": path,
                "count": count_val,
                "batters": len(batters),
                "pitchers": len(pitchers),
                "first_sample": first_sample,
            }
            if batters or pitchers:
                print(
                    f"[ReportTopPlayers] {source_label}: "
                    f"{len(batters)} batters, {len(pitchers)} pitchers",
                    flush=True,
                )
                return batters, pitchers, source_label, debug
        except Exception as e:
            print(f"[ReportTopPlayers] Error fetching {sort}: {e}")
            debug[sort] = {"path": path, "error": str(e)}

    return [], [], "Yahoo Fantasy Points（夢幻積分 PTS）", debug


def _fmt_avg(v: str) -> str:
    """Format rate stats like .350 (drop leading 0)."""
    if not v or v in ("-", "INF"):
        return v or "-"
    try:
        f = float(v)
        s = f"{f:.3f}"
        return s[1:] if s.startswith("0.") else s
    except (ValueError, TypeError):
        return v


def _fmt_era(v: str) -> str:
    """Format rate stats like 1.80 (keep leading digits)."""
    if not v or v in ("-", "INF", "-----"):
        return v or "-"
    try:
        return f"{float(v):.2f}"
    except (ValueError, TypeError):
        return v


def _is_in_reminder_period(today: datetime) -> tuple[bool, str]:
    """Check if today falls within the reminder period.

    Returns (is_active, reason_if_inactive).

    Priority: if KEEPER_REMINDER_START is set, use explicit date range (legacy).
    Otherwise, use the fixed annual window (REMINDER_MONTH / START_DAY / END_DAY).
    """
    today_str = today.strftime("%Y-%m-%d")

    # Legacy mode: explicit date strings
    if KEEPER_REMINDER_START:
        if today_str < KEEPER_REMINDER_START:
            return False, f"Not yet in reminder period (start: {KEEPER_REMINDER_START})"
        if KEEPER_REMINDER_END and today_str > KEEPER_REMINDER_END:
            return False, f"Past reminder period (end: {KEEPER_REMINDER_END})"
        return True, ""

    # Annual window mode: fixed month/day range every year
    if today.month != REMINDER_MONTH:
        return False, f"Not in reminder month (current: {today.month}, target: {REMINDER_MONTH})"
    if today.day < REMINDER_START_DAY:
        return False, f"Before reminder start day (current: {today.day}, start: {REMINDER_START_DAY})"
    if today.day > REMINDER_END_DAY:
        return False, f"Past reminder end day (current: {today.day}, end: {REMINDER_END_DAY})"
    return True, ""


def _daily_reminder_job():
    """Daily job: send reminders if within the configured period."""
    now = datetime.now()
    active, reason = _is_in_reminder_period(now)

    if not active:
        print(f"[Scheduler] {reason}")
        return

    year = now.year
    # Cooldown = interval_days * 24 - 1 hour margin to avoid timezone drift
    cooldown = max(REMINDER_INTERVAL_DAYS * 24 - 1, 23)
    print(f"[Scheduler] Running keeper reminder check for year {year} "
          f"(interval: every {REMINDER_INTERVAL_DAYS} days, cooldown: {cooldown}h)...")

    try:
        from src.notification.reminder import send_reminders
        result = send_reminders(year, sent_by="scheduler", cooldown_hours=cooldown)
        pending_count = len(result["pending_managers"])
        if result["sent_to_group"]:
            print(f"[Scheduler] LINE group reminder sent. "
                  f"Pending teams: {pending_count} "
                  f"({', '.join(result['pending_managers'])})")
        elif result["skipped_reason"] == "all_submitted":
            print("[Scheduler] All teams submitted, no reminder needed.")
        elif result["skipped_reason"] == "cooldown":
            print(f"[Scheduler] Skipped (cooldown). Pending: {pending_count}")
        else:
            print(f"[Scheduler] Failed: {result['error']}")
    except Exception as e:
        print(f"[Scheduler] Error: {e}")


def _daily_rookie_monitor_job():
    """Daily job: check R-contract players for MLB call-ups."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season
    if month < ROOKIE_MONITOR_START_MONTH or month > ROOKIE_MONITOR_END_MONTH:
        print(f"[RookieScheduler] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[RookieScheduler] Checking R-contract call-ups for {year}...")

    try:
        from src.notification.rookie_monitor import send_callup_notifications
        result = send_callup_notifications(year)

        if result["new_callups"] > 0:
            status = "NOTIFIED" if result["notified"] else "DETECTED (notify failed)"
            print(f"[RookieScheduler] {status}: {result['new_callups']} new call-ups "
                  f"({', '.join(result['players'])})")
        else:
            print("[RookieScheduler] No new call-ups detected.")
    except Exception as e:
        print(f"[RookieScheduler] Error: {e}")


def _daily_ar_rank_refresh_job():
    """Daily job: refresh Yahoo AR (Actual Rank) + season stats in a single pass.

    Runs at 18:00 Taiwan time (= 6 AM ET) — after all US games end and Yahoo
    finishes processing stats from the previous day.

    Single pass: sort=AR + out=stats returns AR-sorted players WITH stats in one
    request stream, so we only fetch the top 1500 once (60 calls total).
    O-Rank is pre-season projection and rarely changes — fetch manually via Commissioner.
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[DailyRankStats] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[DailyRankStats] Starting AR-Rank + season stats refresh for {year}...")

    try:
        from api.yahoo_service import YahooTokenError
        from api.database import update_ar_ranks, update_last_season_stats
        from api.routers.commissioner import _fetch_yahoo_players_batch
        from config.settings import get_league_key

        league_key = get_league_key(year)
        if not league_key:
            print(f"[DailyRankStats] No league key for year {year}")
            return

        # One pass: AR-sorted players + season stats (out=stats via batch helper).
        players, errors = _fetch_yahoo_players_batch(
            league_key, sort="AR", sort_type="season",
            max_players=1500, stat_prefix="stat",
        )

        if not players:
            print("[DailyRankStats] No players fetched.")
            if errors:
                print(f"[DailyRankStats] Errors: {errors[:3]}")
            return

        ar_rank_map = {
            p["player_key"]: p["_rank"]
            for p in players
            if p.get("player_key") and p.get("_rank")
        }
        if ar_rank_map:
            update_ar_ranks(year, ar_rank_map)
            print(f"[DailyRankStats] Updated {len(ar_rank_map)} AR rankings")

        update_last_season_stats(year, players, sort_type="season")
        print(f"[DailyRankStats] Updated season stats for {len(players)} players")

        if errors:
            print(f"[DailyRankStats] Partial errors: {errors[:3]}")

        print(f"[DailyRankStats] Refresh complete for {year}")

    except YahooTokenError as e:
        print(f"[DailyRankStats] Token error: {e}")
    except Exception as e:
        print(f"[DailyRankStats] Error: {e}")


def _daily_player_status_job():
    """Daily job: update player IL/DTD/NA/O status from Yahoo API.
    Also detects status changes and sends LINE notifications for owned players."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[StatusUpdate] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[StatusUpdate] Updating player statuses for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_db
        import time

        # Resolve league key
        from config.settings import get_league_key
        league_key = get_league_key(year)
        if not league_key:
            print(f"[StatusUpdate] No league key for year {year}")
            return

        # Step 1: Fetch and update statuses from Yahoo (top 500 by overall rank)
        from api.routers.commissioner import _parse_yahoo_player
        updated = 0
        for start in range(0, 500, 25):
            try:
                path = (
                    f"/league/{league_key}/players"
                    f";start={start};count=25;sort=OR"
                    f";sort_type=season;out=stats"
                )
                data = yahoo_api_get(path)
                league_data = data.get("fantasy_content", {}).get("league", [])
                if len(league_data) < 2:
                    break

                players_section = league_data[1].get("players", {})
                count = players_section.get("count", 0)
                if count == 0:
                    break

                # Update status in DB
                conn = get_db()
                try:
                    cur = conn.cursor()
                    for key, val in players_section.items():
                        if key == "count":
                            continue
                        if isinstance(val, dict) and "player" in val:
                            pdata = val["player"]
                            if isinstance(pdata, list) and len(pdata) >= 1:
                                player_info = _parse_yahoo_player(pdata[0])
                                pk = player_info.get("player_key")
                                status = player_info.get("status")
                                if pk:
                                    cur.execute(
                                        "UPDATE player_rankings SET status = %s "
                                        "WHERE year = %s AND player_key = %s",
                                        (status, year, pk),
                                    )
                                    updated += 1
                    conn.commit()
                    cur.close()
                finally:
                    conn.close()
                time.sleep(1)

            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                else:
                    print(f"[StatusUpdate] Batch error at {start}: {e}")
                    break

        print(f"[StatusUpdate] Updated {updated} player statuses for {year}")

        # Step 2: Batched injury notification (every INJURY_BATCH_DAYS days).
        # DB updates happen daily for UI freshness, but LINE digest only every N days.
        from api.database import get_injury_baseline, save_injury_baseline, get_player_statuses

        baseline, last_checked_at = get_injury_baseline(year)
        current_statuses = get_player_statuses(year)

        if not INJURY_LINE_ENABLED:
            save_injury_baseline(year, current_statuses)
            print("[StatusUpdate] Injury LINE digest disabled; status baseline updated.")
            return

        if baseline is None:
            # First run: seed baseline, don't send.
            save_injury_baseline(year, current_statuses)
            print("[StatusUpdate] Injury baseline seeded, will notify on next cycle.")
            return

        # Cooldown check
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        # last_checked_at from psycopg2 is tz-aware UTC
        days_since = (now - last_checked_at).total_seconds() / 86400 if last_checked_at else 999
        if days_since < INJURY_BATCH_DAYS:
            print(f"[StatusUpdate] {days_since:.1f}d since last injury digest "
                  f"(<{INJURY_BATCH_DAYS}d), skipping LINE send.")
            return

        sent_or_empty = _send_injury_change_notification(year, baseline, current_statuses)
        if sent_or_empty:
            # Only advance baseline on successful send OR when there was nothing to send;
            # LINE API failures keep the baseline so we retry next day.
            save_injury_baseline(year, current_statuses)

    except Exception as e:
        print(f"[StatusUpdate] Error: {e}")


def _send_injury_change_notification(
    year: int,
    old_statuses: dict[str, dict],
    new_statuses: dict[str, dict],
) -> bool:
    """Compare old vs new statuses; send LINE digest. Return True on success/no-op, False on LINE failure."""
    from src.notification.line_service import send_line_group_message

    # Categorize changes (only for owned players)
    new_injuries: list[str] = []      # NULL/empty -> IL/DTD/IL-LT
    recovered: list[str] = []          # IL/DTD -> NULL/empty
    status_changes: list[str] = []     # IL -> DTD, DTD -> IL, etc.

    injury_statuses = {"IL", "IL-LT", "DTD", "NA", "O", "SUSP"}

    for pk, new_info in new_statuses.items():
        owner = new_info.get("owner_manager", "")
        if not owner:
            continue  # Skip FA players

        old_info = old_statuses.get(pk, {})
        old_status = old_info.get("status", "")
        new_status = new_info.get("status", "")

        if old_status == new_status:
            continue  # No change

        name = new_info["player_name"]
        pos = new_info.get("position", "")
        mlb_team = new_info.get("mlb_team", "")
        player_meta = _format_player_meta(pos, mlb_team)
        owner_label = _format_owner_label(new_info)
        label = (
            f"  {name} ({player_meta}) - {owner_label}"
            if player_meta
            else f"  {name} - {owner_label}"
        )

        if (not old_status or old_status not in injury_statuses) and new_status in injury_statuses:
            new_injuries.append(f"{label} -> {new_status}")
        elif old_status in injury_statuses and (not new_status or new_status not in injury_statuses):
            recovered.append(f"{label} -> Active")
        elif old_status in injury_statuses and new_status in injury_statuses and old_status != new_status:
            status_changes.append(f"{label} -> {new_status} (was {old_status})")

    # No changes in the batch window — treat as success so baseline advances.
    if not new_injuries and not recovered and not status_changes:
        print("[StatusUpdate] No injury status changes in batch window.")
        return True

    header = f"[5-Man Keeper League] 傷兵異動彙整（近 {INJURY_BATCH_DAYS} 天）"
    lines = [header, ""]

    if new_injuries:
        lines.append("進入傷兵/異常名單:")
        lines.extend(new_injuries)
        lines.append("")

    if recovered:
        lines.append("解除傷兵名單:")
        lines.extend(recovered)
        lines.append("")

    if status_changes:
        lines.append("狀態變更:")
        lines.extend(status_changes)
        lines.append("")

    total = len(new_injuries) + len(recovered) + len(status_changes)
    message = "\n".join(lines)

    success, error = send_line_group_message(message)
    if success:
        print(f"[StatusUpdate] LINE injury digest sent ({total} changes).")
        return True
    print(f"[StatusUpdate] LINE notification failed: {error}")
    return False


def _daily_transaction_fetch_job():
    """Daily job: fetch latest transactions from Yahoo API during MLB season."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[TransactionFetch] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[TransactionFetch] Fetching transactions for {year}...")

    try:
        from api.yahoo_service import fetch_transactions_full, YahooTokenError
        import json
        from pathlib import Path

        # Resolve league key
        from config.settings import get_league_key
        league_key = get_league_key(year)
        if not league_key:
            print(f"[TransactionFetch] No league key for year {year}")
            return

        result = fetch_transactions_full(league_key)
        new_transactions = result.get("transactions", [])

        if not new_transactions:
            print("[TransactionFetch] No transactions found.")
            return

        # Full overwrite (not append-merge). Yahoo returns the full season
        # history each call, and the container filesystem is ephemeral on
        # redeploy — rewriting the file from scratch every day keeps the data
        # self-healing instead of drifting away from git's checked-in copy.
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tx_file = data_dir / f"yahoo_{year}_transactions.json"

        save_data = {"transactions": new_transactions}
        with open(tx_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

        faab_count = sum(
            1 for t in new_transactions
            if t.get("faab_bid") and t["faab_bid"] > 0
        )
        trade_count = sum(1 for t in new_transactions if t.get("type") == "trade")
        print(
            f"[TransactionFetch] Rewrote {tx_file.name}: "
            f"{len(new_transactions)} total "
            f"(FAAB adds: {faab_count}, trades: {trade_count})"
        )

    except Exception as e:
        print(f"[TransactionFetch] Error: {e}")


def sync_rosters_and_rebuild(year: int) -> dict:
    """Fetch full Yahoo rosters and rebuild next-year snapshot.

    Can be called from scheduler or commissioner API endpoint.

    Args:
        year: The current season year (e.g. 2026)

    Returns:
        dict with message, teams count, players count
    """
    print(f"[SnapshotRebuild] Fetching Yahoo {year} rosters...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_all_teams
        from config.settings import get_league_key
        import json as json_mod
        import time
        from pathlib import Path

        league_key = get_league_key(year)
        if not league_key:
            raise RuntimeError(f"No league key configured for year {year}")

        print(f"[SnapshotRebuild] League key: {league_key}")
        db_teams = get_all_teams()

        # Fetch teams list from Yahoo
        teams_path = f"/league/{league_key}/teams"
        print(f"[SnapshotRebuild] Fetching teams from: {teams_path}")
        teams_data = yahoo_api_get(teams_path)
        league_section = teams_data.get("fantasy_content", {}).get("league", [])
        if len(league_section) < 2:
            raise RuntimeError(
                f"Yahoo API returned no teams data. Response keys: "
                f"{list(teams_data.get('fantasy_content', {}).keys())}"
            )

        teams_section = league_section[1].get("teams", {})
        team_count = teams_section.get("count", 0)
        print(f"[SnapshotRebuild] Found {team_count} teams from Yahoo API")

        if team_count == 0:
            raise RuntimeError("Yahoo API returned 0 teams. Check league key or API status.")

        # Map yahoo_team_id -> manager_name from DB (multiple key formats)
        yahoo_id_to_manager: dict[str, str] = {}
        for db_team in db_teams:
            ytid = db_team.get("yahoo_team_id")
            if ytid:
                ytid_str = str(ytid)
                yahoo_id_to_manager[ytid_str] = db_team["manager_name"]
                # Also index by just the team number (e.g. "1" from "469.l.80910.t.1")
                if "." in ytid_str:
                    yahoo_id_to_manager[ytid_str.split(".")[-1]] = db_team["manager_name"]

        print(f"[SnapshotRebuild] DB team mappings: {yahoo_id_to_manager}")

        # Build full rosters dict: team_key -> {manager, team_name, players[]}
        all_rosters: dict[str, dict] = {}
        # Track player_key -> manager_name for owner_manager sync (replaces
        # the separate _daily_roster_ownership_sync_job that used to re-fetch
        # the same 16 rosters an hour earlier).
        ownership_map: dict[str, str] = {}
        total_players = 0
        skipped_teams: list[str] = []
        debug_logs: list[str] = []

        for i in range(team_count):
            team_entry = teams_section.get(str(i), {}).get("team", [])
            if not team_entry:
                skipped_teams.append(f"team_{i}: no entry")
                continue

            # Extract team info
            team_info_list = team_entry[0] if isinstance(team_entry, list) else []
            team_key = ""
            team_name = ""
            manager_name = ""

            for item in team_info_list:
                if isinstance(item, dict):
                    if "team_key" in item:
                        team_key = item["team_key"]
                    if "name" in item:
                        team_name = item["name"]

            # Resolve manager name from DB mapping (try full key, then number only)
            team_num = team_key.split(".")[-1] if team_key else ""
            manager_name = (
                yahoo_id_to_manager.get(team_key, "")
                or yahoo_id_to_manager.get(team_num, "")
            )
            if not manager_name:
                # Fallback: try from Yahoo managers field
                managers_list = next(
                    (item["managers"] for item in team_info_list
                     if isinstance(item, dict) and "managers" in item),
                    []
                )
                if managers_list and isinstance(managers_list, list):
                    mgr = managers_list[0].get("manager", {})
                    manager_name = mgr.get("nickname", "")

            if not team_key or not manager_name:
                skipped_teams.append(
                    f"team_{i}: key={team_key!r} name={team_name!r} manager={manager_name!r}"
                )
                print(f"[SnapshotRebuild] SKIPPING team_{i}: "
                      f"key={team_key!r} manager={manager_name!r}")
                continue

            # Fetch this team's full roster (with retry on 429)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    roster_path = f"/team/{team_key}/roster"
                    roster_data = yahoo_api_get(roster_path)
                    roster_section = (
                        roster_data.get("fantasy_content", {}).get("team", [])
                    )

                    # Debug: log structure of first team's response
                    if i == 0:
                        import json as _dbg_json
                        dbg = f"roster_section type={type(roster_section).__name__}, len={len(roster_section) if isinstance(roster_section, (list, dict)) else '?'}"
                        debug_logs.append(dbg)
                        print(f"[SnapshotRebuild] DEBUG {dbg}")
                        if isinstance(roster_section, list) and len(roster_section) >= 2:
                            rs1 = roster_section[1]
                            dbg2 = f"rs[1] keys={list(rs1.keys()) if isinstance(rs1, dict) else type(rs1).__name__}"
                            debug_logs.append(dbg2)
                            if isinstance(rs1, dict) and "roster" in rs1:
                                ri = rs1["roster"]
                                dbg3 = f"roster keys={list(ri.keys()) if isinstance(ri, dict) else type(ri).__name__}"
                                debug_logs.append(dbg3)
                                if isinstance(ri, dict) and "players" in ri:
                                    ps = ri["players"]
                                    dbg4 = f"players keys={list(ps.keys())[:5] if isinstance(ps, dict) else type(ps).__name__}, count={ps.get('count','?') if isinstance(ps, dict) else '?'}"
                                    debug_logs.append(dbg4)
                            else:
                                snippet = _dbg_json.dumps(rs1, ensure_ascii=False)[:400]
                                debug_logs.append(f"rs[1]={snippet}")
                        else:
                            snippet = _dbg_json.dumps(roster_section, ensure_ascii=False)[:400]
                            debug_logs.append(f"full={snippet}")

                    players: list[dict] = []
                    if len(roster_section) >= 2:
                        # Yahoo API structure: roster["0"]["players"]["0"]["player"]
                        roster_dict = roster_section[1].get("roster", {})
                        players_section = roster_dict.get("0", {}).get("players", {})
                        p_count = players_section.get("count", 0)
                        for j in range(p_count):
                            player_entry = players_section.get(str(j), {}).get("player", [])
                            if not player_entry:
                                continue
                            # Parse full player data (reuse yahoo_client pattern)
                            info_list = player_entry[0] if isinstance(player_entry, list) else []
                            p = {
                                "name": "", "player_key": "", "position": "",
                                "team": "", "selected_position": "", "status": "",
                            }
                            for item in info_list:
                                if isinstance(item, dict):
                                    if "name" in item:
                                        p["name"] = item["name"].get("full", "")
                                    if "player_key" in item:
                                        p["player_key"] = item["player_key"]
                                    if "display_position" in item:
                                        p["position"] = item["display_position"]
                                    if "editorial_team_abbr" in item:
                                        p["team"] = item["editorial_team_abbr"]
                                    if "status" in item:
                                        p["status"] = item["status"]
                            # Selected position
                            if len(player_entry) > 1 and isinstance(player_entry[1], dict):
                                sp_data = player_entry[1].get("selected_position", [])
                                if isinstance(sp_data, list):
                                    for s in sp_data:
                                        if isinstance(s, dict) and "position" in s:
                                            p["selected_position"] = s["position"]
                            if p["name"]:
                                players.append(p)
                                if p.get("player_key") and manager_name:
                                    ownership_map[p["player_key"]] = manager_name

                    all_rosters[team_key] = {
                        "manager": manager_name,
                        "team_name": team_name,
                        "players": players,
                    }
                    total_players += len(players)
                    print(
                        f"[SnapshotRebuild] {manager_name}: {len(players)} players "
                        f"({len(all_rosters)}/{team_count} teams done)"
                    )
                    time.sleep(1.0)
                    break  # success, exit retry loop

                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait_secs = 15 * (attempt + 1)
                        print(f"[SnapshotRebuild] 429 rate limit for {manager_name}, "
                              f"waiting {wait_secs}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_secs)
                    else:
                        print(f"[SnapshotRebuild] Error fetching {team_key} ({manager_name}): {e}")
                        break

        # Validate: require ALL teams with players before saving
        teams_with_players = sum(1 for t in all_rosters.values() if len(t.get("players", [])) > 0)
        if teams_with_players < 16:
            # Build diagnostic details
            empty_teams = [
                f"{t['manager']}({tk}): {len(t.get('players', []))}p"
                for tk, t in all_rosters.items()
                if len(t.get("players", [])) == 0
            ]
            diag = (
                f"teams_in_api={team_count}, "
                f"teams_matched={len(all_rosters)}, "
                f"teams_with_players={teams_with_players}, "
                f"debug={debug_logs}, "
                f"skipped={skipped_teams}, "
                f"empty={empty_teams}"
            )
            msg = (f"Only {teams_with_players}/{team_count} teams have player data. "
                   f"Aborting to prevent data loss. Diagnostic: {diag}")
            print(f"[SnapshotRebuild] {msg}")
            raise RuntimeError(msg)

        # Save to yahoo_{year}_rosters.json (local file)
        data_dir = Path(__file__).resolve().parents[2] / "data"
        rosters_path = data_dir / f"yahoo_{year}_rosters.json"
        rosters_path.write_text(
            json_mod.dumps(all_rosters, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"[SnapshotRebuild] Saved {rosters_path.name}: "
            f"{len(all_rosters)} teams, {total_players} players"
        )

        # Also save to DB (persists across deployments)
        from api.database import (
            save_synced_roster,
            sync_roster_ownership,
            sync_team_names_from_rosters,
        )
        save_synced_roster(year, all_rosters)
        print(f"[SnapshotRebuild] Saved synced roster to DB (year={year})")

        try:
            team_name_result = sync_team_names_from_rosters(all_rosters)
            print(
                "[SnapshotRebuild] Synced team names: "
                f"{team_name_result['upserted']} upserted, "
                f"{len(team_name_result['skipped'])} skipped"
            )
        except Exception as e:
            print(f"[SnapshotRebuild] Team name sync failed (non-fatal): {e}")

        # Sync owner_manager on player_rankings in the same pass — no extra
        # Yahoo API calls needed since we already parsed every roster.
        if ownership_map:
            sync_roster_ownership(year, ownership_map)
            print(f"[SnapshotRebuild] Synced ownership for {len(ownership_map)} players")

        # Rebuild next-year snapshot
        next_year = year + 1
        try:
            from scripts.build_2027_contracts import main as rebuild_snapshot
            rebuild_snapshot()
            print(f"[SnapshotRebuild] Rebuilt year {next_year} snapshot successfully.")
        except Exception as e:
            print(f"[SnapshotRebuild] Snapshot rebuild error: {e}")

        return {
            "message": f"Synced {year} rosters and rebuilt {next_year} snapshot",
            "year": year,
            "teams": len(all_rosters),
            "total_players": total_players,
        }

    except YahooTokenError as e:
        print(f"[SnapshotRebuild] Token error: {e}")
        raise
    except Exception as e:
        print(f"[SnapshotRebuild] Error: {e}")
        raise


def _daily_roster_snapshot_rebuild_job():
    """Daily scheduler wrapper for sync_rosters_and_rebuild.

    Also syncs owner_manager on player_rankings in the same pass
    (replaces the old separate _daily_roster_ownership_sync_job).
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[SnapshotRebuild] Off-season (month {month}), skipping.")
        return

    try:
        sync_rosters_and_rebuild(now.year)
    except Exception as e:
        print(f"[SnapshotRebuild] Job failed: {e}")


def _daily_games_preview_job(target_id: str = "", dry_run: bool = False) -> dict:
    """Fetch today's MLB schedule and push a compact matchup list to LINE.

    Source: MLB Stats API /schedule?sportId=1&date=YYYY-MM-DD.
    Time basis: ET (eastern time, where MLB's schedule day pivots at midnight
    local-east). We pass today's date in Taiwan time as best-effort; this is
    intended as a one-off verification push so exact calendar pivot doesn't
    matter much.

    Args:
        target_id: if set, push to that LINE id instead of LINE_GROUP_ID
        dry_run: skip the LINE push, return payload for inspection
    """
    import urllib.request
    import json as _json
    from datetime import date as _date

    today = _date.today().isoformat()  # Taiwan time (scheduler tz)
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}"
    print(f"[GamesPreview] Fetching MLB schedule for {today}...")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KeeperLeagueBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        err = f"MLB Stats API fetch failed: {e}"
        print(f"[GamesPreview] {err}")
        if dry_run:
            return {"success": False, "error": err}
        return {"success": False, "error": err}

    games = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            away = g.get("teams", {}).get("away", {}).get("team", {}).get("abbreviation", "")
            home = g.get("teams", {}).get("home", {}).get("team", {}).get("abbreviation", "")
            status = g.get("status", {}).get("detailedState", "")
            game_time = g.get("gameDate", "")  # ISO UTC
            games.append({"away": away, "home": home, "status": status, "time": game_time})

    lines: list[str] = []
    lines.append(f"⚾ 今日 MLB 賽事一覽（{today}）")
    lines.append("━" * 14)
    if not games:
        lines.append("（今日無賽事）")
    else:
        lines.append(f"共 {len(games)} 場")
        lines.append("")
        for g in games:
            away = g["away"] or "?"
            home = g["home"] or "?"
            lines.append(f"  {away:>3}  @  {home:<3}   {g['status']}")
    lines.append("")
    lines.append("（資料來源：MLB Stats API）")
    message = "\n".join(lines)

    if dry_run:
        return {"success": True, "preview": message, "games_count": len(games)}

    from src.notification.line_service import (
        LINE_GROUP_ID,
        send_line_group_message,
        send_line_push_message,
    )
    if target_id:
        success, error = send_line_push_message(target_id, message)
        dest = target_id[:6] + "..."
    else:
        success, error = send_line_group_message(message)
        dest = f"group {LINE_GROUP_ID[:8]}..." if LINE_GROUP_ID else "group(unset)"

    if success:
        print(f"[GamesPreview] Pushed to {dest} ({len(games)} games)")
    else:
        print(f"[GamesPreview] Push failed to {dest}: {error}")
    return {"success": success, "error": error, "games_count": len(games), "dest": dest}


def _weekly_war_report_job(target_id: str = "", dry_run: bool = False) -> dict:
    """Weekly job (Monday 21:00): generate and send weekly war report to LINE.

    Scheduled 3 hours after 18:00 AR-Rank refresh to fully clear any Yahoo
    short-term throttle window before we fetch standings/scoreboard/top players.

    Args:
        target_id: If empty, push to LINE_GROUP_ID (scheduled behavior).
                   If set (U.../C.../R...), push to that target instead — useful
                   for previewing to admin LINE without spamming the group.
        dry_run:   If True, skip LINE send entirely and just return the message
                   text for inspection.

    Returns:
        {"success": bool, "message": str (status or error), "report": str (full text)}
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[WarReport] Off-season (month {month}), skipping.")
        return {"success": False, "message": f"Off-season (month {month})", "report": ""}

    year = now.year
    print(f"[WarReport] Generating weekly war report for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import save_weekly_standings, get_weekly_standings
        from src.notification.line_service import send_line_group_message
        from config.settings import get_league_key
        import time

        league_key = get_league_key(year)
        if not league_key:
            print(f"[WarReport] No league key for year {year}")
            return {"success": False, "message": f"No league key for {year}", "report": ""}

        # --- 1. Get current week from league metadata ---
        meta_path = f"/league/{league_key}/metadata"
        meta_data = yahoo_api_get(meta_path)
        league_meta = meta_data.get("fantasy_content", {}).get("league", [])
        current_week = 1
        if isinstance(league_meta, list):
            for item in league_meta:
                if isinstance(item, dict) and "current_week" in item:
                    current_week = int(item["current_week"])
                    break
        # The report covers the just-completed week (current_week - 1 if games are done)
        # On Monday, Yahoo's "current_week" should be the upcoming week
        report_week = max(current_week - 1, 1)
        print(f"[WarReport] Yahoo current_week={current_week}, reporting week {report_week}")

        # --- 2. Fetch standings ---
        time.sleep(1)
        standings_path = f"/league/{league_key}/standings"
        standings_data = yahoo_api_get(standings_path)
        league_standings = standings_data.get("fantasy_content", {}).get("league", [])
        if len(league_standings) < 2:
            print("[WarReport] No standings data.")
            return {"success": False, "message": "No standings data from Yahoo", "report": ""}

        teams_section = league_standings[1].get("standings", [{}])[0].get("teams", {})
        team_count = teams_section.get("count", 0)
        try:
            team_count = int(team_count or 0)
        except (ValueError, TypeError):
            team_count = 0

        def _safe_int(v, default=0):
            try:
                return int(v) if v not in (None, "") else default
            except (ValueError, TypeError):
                return default

        def _find_section(items, key):
            """Find `key` anywhere inside the tail of team_raw (handles dict or list wrappers)."""
            for elem in items:
                if isinstance(elem, dict) and key in elem:
                    return elem[key]
                if isinstance(elem, list):
                    for sub in elem:
                        if isinstance(sub, dict) and key in sub:
                            return sub[key]
            return {}

        current_standings: list[dict] = []
        for i in range(team_count):
            team_raw = teams_section.get(str(i), {}).get("team", [])
            if not team_raw or not isinstance(team_raw, list):
                continue

            # Element 0: list of info dicts (name, team_key, division_id, managers, ...)
            info_list = team_raw[0] if isinstance(team_raw[0], list) else []
            team_name = ""
            team_key = ""
            manager_name = ""
            division_id = ""
            for item in info_list:
                if not isinstance(item, dict):
                    continue
                if "name" in item:
                    team_name = str(item["name"])
                if "team_key" in item:
                    team_key = str(item["team_key"])
                if "division_id" in item:
                    division_id = str(item["division_id"])
                if "managers" in item:
                    mgrs = item["managers"]
                    if isinstance(mgrs, list) and mgrs and isinstance(mgrs[0], dict):
                        manager_name = str(mgrs[0].get("manager", {}).get("nickname", ""))

            # Element 1+: team_stats / team_points / team_standings (dict- or list-wrapped)
            standing = _find_section(team_raw[1:], "team_standings")
            if not isinstance(standing, dict):
                standing = {}

            rank = _safe_int(standing.get("rank"))
            outcome = standing.get("outcome_totals", {}) if isinstance(standing, dict) else {}
            if not isinstance(outcome, dict):
                outcome = {}
            wins = _safe_int(outcome.get("wins"))
            losses = _safe_int(outcome.get("losses"))
            ties = _safe_int(outcome.get("ties"))

            if i == 0:
                print(
                    f"[WarReport] First team sample: team_name={team_name!r} "
                    f"manager={manager_name!r} division={division_id!r} "
                    f"rank={rank} W-L-T={wins}-{losses}-{ties} "
                    f"standing_keys={list(standing.keys()) if standing else 'EMPTY'}"
                )

            current_standings.append({
                "team_name": team_name,
                "team_key": team_key,
                "manager_name": manager_name,
                "division_id": division_id,
                "rank": rank,
                "wins": wins,
                "losses": losses,
                "ties": ties,
            })

        # Sort by rank; fall back to preserving Yahoo's order if ranks are all 0
        if any(s["rank"] > 0 for s in current_standings):
            current_standings.sort(key=lambda x: x["rank"] or 999)

        # Save current standings for next week's comparison
        save_weekly_standings(year, report_week, current_standings)

        # Load previous week standings for rank change comparison
        prev_standings = get_weekly_standings(year, report_week - 1) if report_week > 1 else []
        prev_rank_map = {s["manager_name"]: s["rank"] for s in prev_standings}

        # --- 3. Fetch scoreboard (matchup results) ---
        time.sleep(1)
        scoreboard_path = f"/league/{league_key}/scoreboard;week={report_week}"
        scoreboard_data = yahoo_api_get(scoreboard_path)
        league_sb = scoreboard_data.get("fantasy_content", {}).get("league", [])
        matchups: list[dict] = []
        if len(league_sb) >= 2:
            sb = league_sb[1].get("scoreboard", {})
            # Handle nested structure
            matchups_section = None
            if "0" in sb and "matchups" in sb["0"]:
                matchups_section = sb["0"]["matchups"]
            elif "matchups" in sb:
                matchups_section = sb["matchups"]

            if matchups_section:
                m_count = matchups_section.get("count", 0)
                for mi in range(m_count):
                    m_raw = matchups_section.get(str(mi), {}).get("matchup", {})
                    teams_data = m_raw.get("0", {}).get("teams", {})
                    t_count = teams_data.get("count", 0)
                    winner_key = m_raw.get("winner_team_key", "")
                    match_teams = []
                    for ti in range(t_count):
                        t_raw = teams_data.get(str(ti), {}).get("team", [])
                        if not t_raw:
                            continue
                        t_info = t_raw[0] if isinstance(t_raw, list) else []
                        t_name = ""
                        t_key = ""
                        t_mgr = ""
                        for item in t_info:
                            if isinstance(item, dict):
                                if "name" in item:
                                    t_name = item["name"]
                                if "team_key" in item:
                                    t_key = item["team_key"]
                                if "managers" in item:
                                    mgrs = item["managers"]
                                    if isinstance(mgrs, list) and mgrs:
                                        t_mgr = mgrs[0].get("manager", {}).get("nickname", "")
                        points = 0.0
                        if len(t_raw) > 1:
                            tp = t_raw[1].get("team_points", {})
                            try:
                                points = float(tp.get("total", 0))
                            except (ValueError, TypeError):
                                points = 0.0
                        match_teams.append({
                            "name": t_name,
                            "manager": t_mgr,
                            "points": points,
                            "is_winner": t_key == winner_key,
                        })
                    if len(match_teams) == 2:
                        matchups.append(match_teams)

        # --- 4. Fetch top 5 hitters and pitchers by Yahoo PTS ---
        time.sleep(1)
        top_batters, top_pitchers, top_player_source, stats_debug = (
            _fetch_yahoo_report_top_players(
                yahoo_api_get,
                league_key,
                sort_type="lastweek",
            )
        )

        # --- 5. Build LINE message (using shared module-level formatting helpers) ---

        # Column width for "ABBR (Manager)" — shared by overall + division sections.
        max_left_vw = max(
            (
                _visual_width(_team_mgr_block(s["team_name"], s["manager_name"]))
                for s in current_standings
            ),
            default=0,
        )

        def _format_standing_line(
            s: dict,
            rank_override: int | None = None,
            indent: str = "",
            show_change: bool = True,
        ) -> str:
            w, l, t = s["wins"], s["losses"], s["ties"]
            rank = rank_override if rank_override is not None else s["rank"]
            left = _pad_right_visual(
                _team_mgr_block(s["team_name"], s["manager_name"]),
                max_left_vw,
            )
            record = f"{w}-{l}-{t}"
            if show_change:
                mgr = s["manager_name"] or "?"
                prev_rank = prev_rank_map.get(mgr)
                if (
                    prev_rank is not None
                    and prev_rank > 0
                    and s["rank"] > 0
                    and prev_rank != s["rank"]
                ):
                    diff = prev_rank - s["rank"]
                    change = f"  ^{diff}" if diff > 0 else f"  v{-diff}"
                else:
                    change = "  --"
            else:
                change = ""
            return f"{indent}{rank:>2}. {left}  {record:>7}{change}"

        # --- Build content sections first, so page_width matches actual content. ---

        # Overall standings
        standings_lines: list[str] = [
            _format_standing_line(s) for s in current_standings
        ]

        # Division standings: group by division_id, rank within each division.
        divisions: dict[str, list[dict]] = {}
        for s in current_standings:
            div = s.get("division_id", "")
            if div:
                divisions.setdefault(div, []).append(s)
        division_blocks: list[tuple[str, list[str]]] = []
        for div_id in sorted(divisions.keys()):
            div_teams = sorted(divisions[div_id], key=lambda x: x["rank"] or 999)
            team_lines = [
                _format_standing_line(
                    s,
                    rank_override=idx,
                    indent="  ",
                    show_change=False,
                )
                for idx, s in enumerate(div_teams, 1)
            ]
            division_blocks.append((f"▸ 分區 {div_id}", team_lines))

        # Matchups — scoreboard style, MLB abbrev, W marker on winner's outer side.
        matchup_lines: list[str] = []
        for idx_m, m in enumerate(matchups):
            t1, t2 = m[0], m[1]
            p1, p2 = t1["points"], t2["points"]
            abbr1 = _fantasy_team_to_mlb_abbr(t1.get("name", "")) or t1.get("manager", "") or "?"
            abbr2 = _fantasy_team_to_mlb_abbr(t2.get("name", "")) or t2.get("manager", "") or "?"
            if t1.get("is_winner"):
                row = f"⭐ {p1:>2.0f} {abbr1:<3}  vs  {abbr2:<3} {p2:>2.0f}"
            elif t2.get("is_winner"):
                row = f"   {p1:>2.0f} {abbr1:<3}  vs  {abbr2:<3} {p2:>2.0f} ⭐"
            else:
                row = f"   {p1:>2.0f} {abbr1:<3}  vs  {abbr2:<3} {p2:>2.0f}"
            matchup_lines.append(row)
            if idx_m < len(matchups) - 1:
                matchup_lines.append("")

        # Top batters — 3 lines per player: name / rate stats / counting stats.
        batter_lines: list[str] = []
        for idx, b in enumerate(top_batters[:5], 1):
            name = b.get("name", "?")
            pos = b.get("position", "")
            owner = b.get("owner_team", "FA")
            owner_abbr = _fantasy_team_to_mlb_abbr(owner) or owner
            st = b.get("stats", {})
            h = st.get("H", "-")
            ab = st.get("AB", "-")
            avg = _fmt_avg(st.get("AVG", "-"))
            ops = _fmt_avg(st.get("OPS", "-"))
            hr = st.get("HR", "0")
            rbi = st.get("RBI", "0")
            r = st.get("R", "0")
            sb = st.get("SB", "0")
            batter_lines.append(f" {idx}. {name} {pos} {owner_abbr}")
            batter_lines.append(f"    {h}-{ab}  {avg}/{ops}")
            batter_lines.append(f"    {hr}HR {rbi}RBI {r}R {sb}SB")

        # Top pitchers — 3 lines per player: name / IP + counting / ERA / WHIP.
        # SP hides SV/HLD, RP hides QS.
        pitcher_lines: list[str] = []
        for idx, p in enumerate(top_pitchers[:5], 1):
            name = p.get("name", "?")
            pos = p.get("position", "")
            owner = p.get("owner_team", "FA")
            owner_abbr = _fantasy_team_to_mlb_abbr(owner) or owner
            st = p.get("stats", {})
            ip = st.get("IP", "-")
            w = st.get("W", "0")
            sv = st.get("SV", "0")
            hld = st.get("HLD", "0")
            k = st.get("K", "0")
            era = _fmt_era(st.get("ERA", "-"))
            whip = _fmt_era(st.get("WHIP", "-"))
            qs = st.get("QS", "0")
            pos_upper = (pos or "").upper()
            is_sp = "SP" in pos_upper
            is_rp = "RP" in pos_upper
            counting_parts = [f"{w}W", f"{k}K"]
            if is_sp and not is_rp:
                counting_parts.append(f"{qs}QS")
            elif is_rp and not is_sp:
                counting_parts.extend([f"{sv}SV", f"{hld}HLD"])
            else:
                counting_parts.extend([f"{qs}QS", f"{sv}SV", f"{hld}HLD"])
            counting = " ".join(counting_parts)
            pitcher_lines.append(f" {idx}. {name} {pos} {owner_abbr}")
            pitcher_lines.append(f"    {ip} IP  {counting}")
            pitcher_lines.append(f"    {era} ERA / {whip} WHIP")

        if not batter_lines:
            batter_lines = _format_stats_unavailable("本週最佳打者")
        if not pitcher_lines:
            pitcher_lines = _format_stats_unavailable("本週最佳投手")

        # page_width: widest non-blank line (content + section headers), floor 28.
        # Headers are included so that long titles like "【本週最佳打者】(...)"
        # still receive symmetric padding when _center() is applied.
        all_content: list[str] = []
        all_content.extend(standings_lines)
        for _sub_header, team_lines in division_blocks:
            all_content.extend(team_lines)
        all_content.extend(l for l in matchup_lines if l)
        all_content.extend(batter_lines)
        all_content.extend(pitcher_lines)

        section_headers: list[str] = ["【聯盟總排名】"]
        if division_blocks:
            section_headers.append("【分區排名】")
            section_headers.extend(h for h, _ in division_blocks)
        if matchup_lines:
            section_headers.append("【本週對戰】")
        if batter_lines:
            section_headers.append("【本週最佳打者】")
        if pitcher_lines:
            section_headers.append("【本週最佳投手】")

        page_width = max(
            (_visual_width(l) for l in (all_content + section_headers) if l and l.strip()),
            default=28,
        )
        page_width = max(page_width, 28)
        # Force even so centered (even-width) text is pixel-symmetric in fullwidths.
        if page_width % 2 == 1:
            page_width += 1

        # Divider spans full page width — clean, always aligned with content edges.
        divider_raw = "━" * (page_width // 2)
        divider_line = divider_raw

        # Assemble final message with centered section headers.
        lines: list[str] = [
            divider_line,
            _center_line("5-Man Keeper League", page_width),
            _center_line(f"第 {report_week} 週戰報", page_width),
            divider_line,
            "",
            _center_line("【聯盟總排名】", page_width),
        ]
        lines.extend(standings_lines)
        lines.append("")

        if division_blocks:
            lines.append(_center_line("【分區排名】", page_width))
            for sub_header, team_lines in division_blocks:
                lines.append(sub_header)
                lines.extend(team_lines)
            lines.append("")

        if matchup_lines:
            lines.append(_center_line("【本週對戰】", page_width))
            for ml in matchup_lines:
                lines.append(_center_line(ml, page_width) if ml else ml)
            lines.append("")

        if batter_lines:
            lines.append(_center_line("【本週最佳打者】", page_width))
            lines.extend(batter_lines)
            lines.append("")

        if pitcher_lines:
            lines.append(_center_line("【本週最佳投手】", page_width))
            lines.extend(pitcher_lines)
            lines.append("")

        lines.append(divider_line)
        lines.append(f"最佳球員排名依據：{top_player_source}")

        # --- 6. AI commentary (OpenAI; no-op if OPENAI_API_KEY not set) ---
        try:
            from src.notification.ai_summary import generate_weekly_ai_summary
            ai_text = generate_weekly_ai_summary(
                report_week,
                current_standings,
                prev_standings,
            )
            if ai_text:
                lines.append("")
                lines.append(_center_line("【AI 短評】", page_width))
                lines.append(ai_text)
        except Exception as e:
            print(f"[WarReport] AI summary failed (non-fatal): {e}")

        message = "\n".join(lines)

        if dry_run:
            print(f"[WarReport] Dry-run: returning week {report_week} report text.")
            return {
                "success": True,
                "message": "Dry-run (no LINE push)",
                "report": message,
                "stats_debug": stats_debug,
            }

        # Send LINE message
        if target_id:
            from src.notification.line_service import send_line_push_message
            success, error = send_line_push_message(target_id, message)
            destination = f"target {target_id[:6]}..."
        else:
            success, error = send_line_group_message(message)
            destination = "LINE group"

        if success:
            print(f"[WarReport] Week {report_week} war report sent to {destination}.")
            return {"success": True, "message": f"Sent to {destination}", "report": message}
        print(f"[WarReport] LINE send failed: {error}")
        return {"success": False, "message": f"LINE send failed: {error}", "report": message}

    except YahooTokenError as e:
        print(f"[WarReport] Token error: {e}")
        return {"success": False, "message": f"Token error: {e}", "report": ""}
    except Exception as e:
        print(f"[WarReport] Error: {e}")
        return {"success": False, "message": f"Error: {e}", "report": ""}


def _monthly_war_report_job(target_id: str = "", dry_run: bool = False) -> dict:
    """Monthly job (1st of each month, 20:45): generate monthly summary report.

    Styled to match the weekly war report: centered headers, ABBR (manager),
    3-line per-player stat blocks, division standings, playoff-berth distance,
    full transaction list, and optional AI commentary.

    Args:
        target_id: If empty, push to LINE_GROUP_ID. If set, push to that target.
        dry_run:   If True, skip LINE push and return the composed text only.
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (April-October; skips March since no full month data yet)
    if month < 4 or month > 10:
        print(f"[MonthlyReport] Off-season or too early (month {month}), skipping.")
        return {"success": False, "message": f"Off-season (month {month})", "report": ""}

    year = now.year
    report_month = month - 1  # Report covers the previous month
    month_names = {3: "3月", 4: "4月", 5: "5月", 6: "6月",
                   7: "7月", 8: "8月", 9: "9月", 10: "10月"}
    month_label = month_names.get(report_month, f"{report_month}月")

    print(f"[MonthlyReport] Generating {month_label} report for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_weekly_standings
        from src.notification.line_service import (
            send_line_group_message,
            send_line_push_message,
        )
        from config.settings import get_league_key
        import time
        import json
        from pathlib import Path

        league_key = get_league_key(year)
        if not league_key:
            print(f"[MonthlyReport] No league key for year {year}")
            return {"success": False, "message": f"No league key for {year}", "report": ""}

        # --- 1. Current week (to bracket the report month's weeks) ---
        meta_path = f"/league/{league_key}/metadata"
        meta_data = yahoo_api_get(meta_path)
        league_meta = meta_data.get("fantasy_content", {}).get("league", [])
        current_week = 1
        if isinstance(league_meta, list):
            for item in league_meta:
                if isinstance(item, dict) and "current_week" in item:
                    current_week = int(item["current_week"])
                    break
        report_week_end = max(current_week - 1, 1)

        def _safe_int(v, default=0):
            try:
                return int(v) if v not in (None, "") else default
            except (ValueError, TypeError):
                return default

        def _find_section(items, key):
            for elem in items:
                if isinstance(elem, dict) and key in elem:
                    return elem[key]
                if isinstance(elem, list):
                    for sub in elem:
                        if isinstance(sub, dict) and key in sub:
                            return sub[key]
            return {}

        # --- 2. Current standings (month-end snapshot) ---
        time.sleep(1)
        standings_path = f"/league/{league_key}/standings"
        standings_data = yahoo_api_get(standings_path)
        league_standings = standings_data.get("fantasy_content", {}).get("league", [])
        if len(league_standings) < 2:
            print("[MonthlyReport] No standings data.")
            return {"success": False, "message": "No standings data", "report": ""}

        teams_section = league_standings[1].get("standings", [{}])[0].get("teams", {})
        team_count = _safe_int(teams_section.get("count", 0))

        current_standings: list[dict] = []
        for i in range(team_count):
            team_raw = teams_section.get(str(i), {}).get("team", [])
            if not team_raw or not isinstance(team_raw, list):
                continue
            info_list = team_raw[0] if isinstance(team_raw[0], list) else []
            team_name = ""
            team_key = ""
            manager_name = ""
            division_id = ""
            for item in info_list:
                if not isinstance(item, dict):
                    continue
                if "name" in item:
                    team_name = str(item["name"])
                if "team_key" in item:
                    team_key = str(item["team_key"])
                if "division_id" in item:
                    division_id = str(item["division_id"])
                if "managers" in item:
                    mgrs = item["managers"]
                    if isinstance(mgrs, list) and mgrs and isinstance(mgrs[0], dict):
                        manager_name = str(mgrs[0].get("manager", {}).get("nickname", ""))
            standing = _find_section(team_raw[1:], "team_standings")
            if not isinstance(standing, dict):
                standing = {}
            rank = _safe_int(standing.get("rank"))
            outcome = standing.get("outcome_totals", {}) if isinstance(standing, dict) else {}
            if not isinstance(outcome, dict):
                outcome = {}
            wins = _safe_int(outcome.get("wins"))
            losses = _safe_int(outcome.get("losses"))
            ties = _safe_int(outcome.get("ties"))
            current_standings.append({
                "team_name": team_name,
                "team_key": team_key,
                "manager_name": manager_name,
                "division_id": division_id,
                "rank": rank,
                "wins": wins,
                "losses": losses,
                "ties": ties,
            })
        if any(s["rank"] > 0 for s in current_standings):
            current_standings.sort(key=lambda x: x["rank"] or 999)

        # Start-of-month standings — we stored each week's snapshot, so use the
        # week ~4 weeks before month-end as the baseline for rank/record delta.
        month_start_week = max(report_week_end - 4, 1)
        prev_month_standings = get_weekly_standings(year, month_start_week)
        prev_rank_map = {s["manager_name"]: s["rank"] for s in prev_month_standings}

        # --- 3. Monthly scoreboard (aggregate weekly W-L for teams) ---
        time.sleep(1)
        team_monthly_record: dict[str, dict] = {}
        for wk in range(month_start_week + 1, report_week_end + 1):
            try:
                sb_path = f"/league/{league_key}/scoreboard;week={wk}"
                sb_data = yahoo_api_get(sb_path)
                sb_league = sb_data.get("fantasy_content", {}).get("league", [])
                if len(sb_league) < 2:
                    continue
                sb = sb_league[1].get("scoreboard", {})
                matchups_section = (
                    sb["0"]["matchups"]
                    if "0" in sb and "matchups" in sb["0"]
                    else sb.get("matchups")
                )
                if not matchups_section:
                    continue

                m_count = _safe_int(matchups_section.get("count", 0))
                for mi in range(m_count):
                    m_raw = matchups_section.get(str(mi), {}).get("matchup", {})
                    teams_data = m_raw.get("0", {}).get("teams", {})
                    winner_key = m_raw.get("winner_team_key", "")
                    t_count = _safe_int(teams_data.get("count", 0))

                    match_info = []
                    for ti in range(t_count):
                        t_raw = teams_data.get(str(ti), {}).get("team", [])
                        if not t_raw:
                            continue
                        t_info = t_raw[0] if isinstance(t_raw, list) else []
                        t_key = ""
                        t_mgr = ""
                        for item in t_info:
                            if isinstance(item, dict):
                                if "team_key" in item:
                                    t_key = item["team_key"]
                                if "managers" in item:
                                    mgrs = item["managers"]
                                    if isinstance(mgrs, list) and mgrs:
                                        t_mgr = mgrs[0].get("manager", {}).get("nickname", "")
                        match_info.append({"key": t_key, "mgr": t_mgr})

                    if len(match_info) == 2:
                        for mi_t in match_info:
                            mgr = mi_t["mgr"] or "?"
                            team_monthly_record.setdefault(mgr, {"w": 0, "l": 0, "t": 0})
                            if mi_t["key"] == winner_key:
                                team_monthly_record[mgr]["w"] += 1
                            elif winner_key:
                                team_monthly_record[mgr]["l"] += 1
                            else:
                                team_monthly_record[mgr]["t"] += 1

                time.sleep(0.6)
            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                else:
                    print(f"[MonthlyReport] Scoreboard error week {wk}: {e}")

        # --- 4. Top 5 hitters/pitchers using Yahoo PTS ---
        time.sleep(1)
        top_batters, top_pitchers, top_player_source, stats_debug = (
            _fetch_yahoo_report_top_players(
                yahoo_api_get,
                league_key,
                sort_type="lastmonth",
            )
        )

        # --- 5. Transaction summary (read local JSON) ---
        month_trades = 0
        month_adds = 0
        month_drops = 0
        trade_details: list[str] = []
        try:
            data_dir = Path(__file__).resolve().parent.parent.parent / "data"
            tx_file = data_dir / f"yahoo_{year}_transactions.json"
            if tx_file.exists():
                with open(tx_file, "r", encoding="utf-8") as f:
                    tx_data = json.load(f)
                all_tx = tx_data.get("transactions", [])
                for tx in all_tx:
                    ts = tx.get("timestamp", "")
                    if not ts:
                        continue
                    try:
                        from datetime import datetime as dt_cls
                        tx_date = dt_cls.fromtimestamp(int(ts))
                        if tx_date.year != year or tx_date.month != report_month:
                            continue
                    except (ValueError, TypeError):
                        continue
                    tx_type = tx.get("type", "")
                    if tx_type == "trade":
                        month_trades += 1
                        players = tx.get("players", [])
                        names = [p.get("name", "?") for p in players[:4]]
                        if names:
                            trade_details.append(", ".join(names))
                    elif tx_type in ("add", "add/drop"):
                        month_adds += 1
                        if "drop" in tx_type:
                            month_drops += 1
                    elif tx_type == "drop":
                        month_drops += 1
        except Exception as e:
            print(f"[MonthlyReport] Transaction summary error: {e}")

        # --- 6. Rookie watch: owned R-contract players + unowned top prospects ---
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        rookie_r_lines, rookie_fa_lines, rookie_watch_debug = _build_rookie_watch_lines(
            year,
            report_month,
            month_label,
            data_dir,
        )

        # --- 7. Build LINE message (weekly-style layout) ---

        # Column width shared by overall + division lines.
        max_left_vw = max(
            (
                _visual_width(_team_mgr_block(s["team_name"], s["manager_name"]))
                for s in current_standings
            ),
            default=0,
        )

        def _format_standing_line(
            s: dict,
            rank_override: int | None = None,
            indent: str = "",
            show_change: bool = True,
        ) -> str:
            w, l, t = s["wins"], s["losses"], s["ties"]
            rank = rank_override if rank_override is not None else s["rank"]
            left = _pad_right_visual(
                _team_mgr_block(s["team_name"], s["manager_name"]),
                max_left_vw,
            )
            record = f"{w}-{l}-{t}"
            if show_change:
                mgr = s["manager_name"] or "?"
                prev_rank = prev_rank_map.get(mgr)
                if (
                    prev_rank is not None
                    and prev_rank > 0
                    and s["rank"] > 0
                    and prev_rank != s["rank"]
                ):
                    diff = prev_rank - s["rank"]
                    change = f"  ^{diff}" if diff > 0 else f"  v{-diff}"
                else:
                    change = "  --"
            else:
                change = ""
            return f"{indent}{rank:>2}. {left}  {record:>7}{change}"

        # Overall standings.
        standings_lines = [_format_standing_line(s) for s in current_standings]

        # Division standings.
        divisions: dict[str, list[dict]] = {}
        for s in current_standings:
            div = s.get("division_id", "")
            if div:
                divisions.setdefault(div, []).append(s)
        division_blocks: list[tuple[str, list[str]]] = []
        for div_id in sorted(divisions.keys()):
            div_teams = sorted(divisions[div_id], key=lambda x: x["rank"] or 999)
            team_lines = [
                _format_standing_line(s, rank_override=idx, indent="  ", show_change=False)
                for idx, s in enumerate(div_teams, 1)
            ]
            division_blocks.append((f"▸ 分區 {div_id}", team_lines))

        # Monthly W-L-T ranking (hot/cold — sorted best to worst for the month).
        monthly_record_lines: list[str] = []
        if team_monthly_record:
            sorted_monthly = sorted(
                team_monthly_record.items(),
                key=lambda x: (x[1]["w"], -x[1]["l"]),
                reverse=True,
            )
            max_mgr_vw = max(
                (_visual_width(mgr) for mgr, _ in sorted_monthly),
                default=0,
            )
            for idx, (mgr, rec) in enumerate(sorted_monthly, 1):
                left = _pad_right_visual(mgr or "?", max_mgr_vw)
                monthly_record_lines.append(
                    f" {idx:>2}. {left}  {rec['w']}-{rec['l']}-{rec['t']}"
                )

        # Playoff gate — wins relative to 8th place (top 8 = playoffs).
        playoff_lines: list[str] = []
        if len(current_standings) >= 8:
            eighth = current_standings[7]
            eighth_wins = eighth["wins"]
            eighth_mgr = eighth["manager_name"] or "?"
            max_mgr_vw_po = max(
                (_visual_width(s["manager_name"] or "?") for s in current_standings),
                default=0,
            )
            for s in current_standings:
                mgr = s["manager_name"] or "?"
                left = _pad_right_visual(mgr, max_mgr_vw_po)
                if s["rank"] == 8:
                    marker = "—— 第 8 名 ——"
                    playoff_lines.append(f"  {left}  {marker}")
                else:
                    diff = s["wins"] - eighth_wins
                    if diff > 0:
                        tag = f"+{diff}W"
                    elif diff < 0:
                        tag = f"{diff}W"
                    else:
                        tag = "同勝"
                    playoff_lines.append(f"  {left}  {tag}")
            playoff_lines.append("")
            playoff_lines.append(f"  （以第 8 名 {eighth_mgr} 的勝場為基準）")

        # Top batters — 3 lines per player (weekly-style).
        batter_lines: list[str] = []
        for idx, b in enumerate(top_batters[:5], 1):
            name = b.get("name", "?")
            pos = b.get("position", "")
            owner = b.get("owner_team", "FA")
            owner_abbr = _fantasy_team_to_mlb_abbr(owner) or owner
            st = b.get("stats", {})
            h = st.get("H", "-")
            ab = st.get("AB", "-")
            avg = _fmt_avg(st.get("AVG", "-"))
            ops = _fmt_avg(st.get("OPS", "-"))
            hr = st.get("HR", "0")
            rbi = st.get("RBI", "0")
            r = st.get("R", "0")
            sb = st.get("SB", "0")
            batter_lines.append(f" {idx}. {name} {pos} {owner_abbr}")
            batter_lines.append(f"    {h}-{ab}  {avg}/{ops}")
            batter_lines.append(f"    {hr}HR {rbi}RBI {r}R {sb}SB")

        # Top pitchers — 3 lines per player (weekly-style, position-aware).
        pitcher_lines: list[str] = []
        for idx, p in enumerate(top_pitchers[:5], 1):
            name = p.get("name", "?")
            pos = p.get("position", "")
            owner = p.get("owner_team", "FA")
            owner_abbr = _fantasy_team_to_mlb_abbr(owner) or owner
            st = p.get("stats", {})
            ip = st.get("IP", "-")
            w = st.get("W", "0")
            sv = st.get("SV", "0")
            hld = st.get("HLD", "0")
            k = st.get("K", "0")
            era = _fmt_era(st.get("ERA", "-"))
            whip = _fmt_era(st.get("WHIP", "-"))
            qs = st.get("QS", "0")
            pos_upper = (pos or "").upper()
            is_sp = "SP" in pos_upper
            is_rp = "RP" in pos_upper
            counting_parts = [f"{w}W", f"{k}K"]
            if is_sp and not is_rp:
                counting_parts.append(f"{qs}QS")
            elif is_rp and not is_sp:
                counting_parts.extend([f"{sv}SV", f"{hld}HLD"])
            else:
                counting_parts.extend([f"{qs}QS", f"{sv}SV", f"{hld}HLD"])
            pitcher_lines.append(f" {idx}. {name} {pos} {owner_abbr}")
            pitcher_lines.append(f"    {ip} IP  {' '.join(counting_parts)}")
            pitcher_lines.append(f"    {era} ERA / {whip} WHIP")

        if not batter_lines:
            batter_lines = _format_stats_unavailable(f"{month_label}最佳打者")
        if not pitcher_lines:
            pitcher_lines = _format_stats_unavailable(f"{month_label}最佳投手")

        # Transaction summary — totals + full trade list.
        tx_lines: list[str] = []
        if month_trades or month_adds or month_drops:
            tx_lines.append(
                f"  交易: {month_trades} 筆 | 撿人: {month_adds} 筆 | 釋出: {month_drops} 筆"
            )
            if trade_details:
                tx_lines.append("")
                tx_lines.append("  交易明細：")
                for nt in trade_details:
                    tx_lines.append(f"    • {nt}")

        # Collect content to size the page width.
        all_content: list[str] = []
        all_content.extend(standings_lines)
        for _sh, lines_sub in division_blocks:
            all_content.extend(lines_sub)
        all_content.extend(monthly_record_lines)
        all_content.extend(l for l in playoff_lines if l)
        all_content.extend(batter_lines)
        all_content.extend(pitcher_lines)
        all_content.extend(l for l in tx_lines if l)
        all_content.extend(rookie_r_lines)
        all_content.extend(rookie_fa_lines)

        section_headers: list[str] = ["【聯盟總排名】"]
        if division_blocks:
            section_headers.append("【分區排名】")
            section_headers.extend(h for h, _ in division_blocks)
        if monthly_record_lines:
            section_headers.append(f"【{month_label}戰績排名】")
        if playoff_lines:
            section_headers.append("【季後賽門票】")
        if batter_lines:
            section_headers.append(f"【{month_label}最佳打者】")
        if pitcher_lines:
            section_headers.append(f"【{month_label}最佳投手】")
        if tx_lines:
            section_headers.append(f"【{month_label}交易摘要】")
        if rookie_r_lines:
            section_headers.append("【R 約新秀觀察】")
        if rookie_fa_lines:
            section_headers.append("【未持有新秀觀察】")

        page_width = max(
            (_visual_width(l) for l in (all_content + section_headers) if l and l.strip()),
            default=28,
        )
        page_width = max(page_width, 28)
        if page_width % 2 == 1:
            page_width += 1

        divider_line = "━" * (page_width // 2)

        lines: list[str] = [
            divider_line,
            _center_line("5-Man Keeper League", page_width),
            _center_line(f"{year} {month_label}月報", page_width),
            divider_line,
            "",
            _center_line("【聯盟總排名】", page_width),
        ]
        lines.extend(standings_lines)
        lines.append("")

        if division_blocks:
            lines.append(_center_line("【分區排名】", page_width))
            for sub_header, team_lines in division_blocks:
                lines.append(sub_header)
                lines.extend(team_lines)
            lines.append("")

        if monthly_record_lines:
            lines.append(_center_line(f"【{month_label}戰績排名】", page_width))
            lines.extend(monthly_record_lines)
            lines.append("")

        if playoff_lines:
            lines.append(_center_line("【季後賽門票】", page_width))
            lines.extend(playoff_lines)
            lines.append("")

        if batter_lines:
            lines.append(_center_line(f"【{month_label}最佳打者】", page_width))
            lines.extend(batter_lines)
            lines.append("")

        if pitcher_lines:
            lines.append(_center_line(f"【{month_label}最佳投手】", page_width))
            lines.extend(pitcher_lines)
            lines.append("")

        if tx_lines:
            lines.append(_center_line(f"【{month_label}交易摘要】", page_width))
            lines.extend(tx_lines)
            lines.append("")

        if rookie_r_lines:
            lines.append(_center_line("【R 約新秀觀察】", page_width))
            lines.extend(rookie_r_lines)
            lines.append("")

        if rookie_fa_lines:
            lines.append(_center_line("【未持有新秀觀察】", page_width))
            lines.extend(rookie_fa_lines)
            lines.append("")

        lines.append(divider_line)
        lines.append(f"最佳球員排名依據：{top_player_source}")
        lines.append("新秀觀察來源：Yahoo rosters + MLB Stats API")

        # AI commentary (monthly variant).
        try:
            from src.notification.ai_summary import generate_monthly_ai_summary
            ai_text = generate_monthly_ai_summary(
                month_label,
                current_standings,
                prev_month_standings,
                team_monthly_record,
            )
            if ai_text:
                lines.append("")
                lines.append(_center_line("【AI 短評】", page_width))
                lines.append(ai_text)
        except Exception as e:
            print(f"[MonthlyReport] AI summary failed (non-fatal): {e}")

        message = "\n".join(lines)

        if dry_run:
            print(f"[MonthlyReport] Dry-run: returning {month_label} report text.")
            return {
                "success": True,
                "message": "Dry-run (no LINE push)",
                "report": message,
                "stats_debug": stats_debug,
                "rookie_watch_debug": rookie_watch_debug,
            }

        if target_id:
            success, error = send_line_push_message(target_id, message)
            dest = f"target {target_id[:6]}..."
        else:
            success, error = send_line_group_message(message)
            dest = "LINE group"

        if success:
            print(f"[MonthlyReport] {month_label} report sent to {dest}.")
            return {"success": True, "message": f"Sent to {dest}", "report": message}
        print(f"[MonthlyReport] LINE send failed: {error}")
        return {"success": False, "message": f"LINE send failed: {error}", "report": message}

    except YahooTokenError as e:
        print(f"[MonthlyReport] Token error: {e}")
        return {"success": False, "message": f"Token error: {e}", "report": ""}
    except Exception as e:
        print(f"[MonthlyReport] Error: {e}")
        return {"success": False, "message": f"Error: {e}", "report": ""}


def _prospect_ranking_update_job():
    """Annual job (Aug 15): fetch MLB Pipeline prospect data and compare with league R-contract players."""
    now = datetime.now()
    # Only run on August 15
    if now.month != 8 or now.day != 15:
        return

    year = now.year
    print(f"[ProspectUpdate] Fetching MLB prospect rankings for {year}...")

    try:
        import httpx
        import time
        from src.notification.line_service import send_line_group_message
        from src.notification.rookie_monitor import _load_r_contract_players

        MLB_BASE = "https://statsapi.mlb.com/api/v1"

        # --- 1. Fetch MLB Pipeline prospect data ---
        # Try the draft/prospects endpoint for the current year
        prospects: list[dict] = []
        try:
            resp = httpx.get(
                f"{MLB_BASE}/draft/prospects/{year}",
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            # Parse prospects from response
            prospect_list = data.get("prospects", [])
            for p in prospect_list:
                person = p.get("person", {})
                if not person:
                    continue
                prospects.append({
                    "name": person.get("fullName", ""),
                    "mlb_id": person.get("id"),
                    "position": person.get("primaryPosition", {}).get("abbreviation", ""),
                    "team": p.get("team", {}).get("abbreviation",
                            person.get("currentTeam", {}).get("abbreviation", "")),
                    "rank": p.get("rank", p.get("pickNumber", 0)),
                })
        except Exception as e:
            print(f"[ProspectUpdate] draft/prospects endpoint error: {e}")

        # Also try the people/search approach for a broader list
        if not prospects:
            print("[ProspectUpdate] Trying alternative: top prospect search...")
            try:
                # MLB Stats API: search for prospect-tagged players
                resp = httpx.get(
                    f"{MLB_BASE}/people/search",
                    params={
                        "names": "",
                        "sportId": 11,  # Minor leagues
                        "season": year,
                        "hydrate": "currentTeam",
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    people = resp.json().get("people", [])
                    for person in people[:200]:
                        prospects.append({
                            "name": person.get("fullName", ""),
                            "mlb_id": person.get("id"),
                            "position": person.get("primaryPosition", {}).get("abbreviation", ""),
                            "team": person.get("currentTeam", {}).get("abbreviation", ""),
                            "rank": 0,
                        })
            except Exception as e:
                print(f"[ProspectUpdate] Alternative search error: {e}")

        print(f"[ProspectUpdate] Fetched {len(prospects)} prospects from MLB API")

        # --- 2. Load league R-contract players ---
        r_players = _load_r_contract_players(year)
        if not r_players:
            print("[ProspectUpdate] No R-contract players found in league")
            # Still send a summary even if no R players
            r_players = []

        print(f"[ProspectUpdate] League has {len(r_players)} R-contract players")

        # --- 3. Cross-reference: check which R players appear in prospect list ---
        # Normalize names for matching (lowercase, strip accents, etc.)
        prospect_name_map: dict[str, dict] = {}
        for p in prospects:
            name_key = p["name"].lower().strip()
            prospect_name_map[name_key] = p
            # Also try last name only for fuzzy matching
            parts = name_key.split()
            if len(parts) >= 2:
                prospect_name_map[parts[-1]] = p

        matched: list[dict] = []
        unmatched: list[dict] = []

        for rp in r_players:
            rp_name = rp["name"].lower().strip()
            # Clean parenthetical nicknames: "Roki Sasaki (佐々木朗希)" -> "roki sasaki"
            clean_name = rp_name.split("(")[0].strip()

            match = prospect_name_map.get(clean_name)
            if not match:
                # Try last name
                parts = clean_name.split()
                if len(parts) >= 2:
                    match = prospect_name_map.get(parts[-1])

            if not match:
                # Try MLB Stats API person search for individual player
                try:
                    search_name = rp["name"].split("(")[0].strip()
                    resp = httpx.get(
                        f"{MLB_BASE}/people/search",
                        params={"names": search_name, "hydrate": "currentTeam"},
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        people = resp.json().get("people", [])
                        if people:
                            person = people[0]
                            match = {
                                "name": person.get("fullName", ""),
                                "mlb_id": person.get("id"),
                                "position": person.get("primaryPosition", {}).get("abbreviation", ""),
                                "team": person.get("currentTeam", {}).get("abbreviation", ""),
                                "rank": 0,
                                "age": person.get("currentAge"),
                                "debut": person.get("mlbDebutDate", ""),
                            }
                    time.sleep(0.5)
                except Exception:
                    pass

            if match:
                matched.append({
                    **rp,
                    "prospect_info": match,
                })
            else:
                unmatched.append(rp)

        # --- 4. Build and send LINE notification ---
        lines = [
            f"[5-Man Keeper League] {year} 新秀排名更新",
            f"MLB Prospect Rankings Update",
            f"",
            f"資料來源: MLB Stats API ({now.strftime('%Y-%m-%d')})",
            f"聯盟 R 約球員: {len(r_players)} 名",
            f"",
        ]

        if matched:
            lines.append("-- 聯盟 R 約球員 MLB 資訊 --")
            for m in matched:
                pi = m["prospect_info"]
                rank_str = f"#{pi['rank']}" if pi.get("rank") else ""
                age_str = f", {pi['age']}歲" if pi.get("age") else ""
                debut_str = f" (已升大聯盟 {pi['debut']})" if pi.get("debut") else ""
                player_meta = _format_player_meta(
                    pi.get("position", m["position"]),
                    pi.get("team", m["mlb_team"]),
                )
                player_label = (
                    f"{m['name']} ({player_meta})" if player_meta else m["name"]
                )
                lines.append(
                    f"  {player_label} - {_format_owner_label(m)}"
                )
                if rank_str or age_str or debut_str:
                    lines.append(f"    {rank_str}{age_str}{debut_str}")
            lines.append("")

        if unmatched:
            lines.append("-- 未在 MLB API 中找到 --")
            for u in unmatched:
                player_meta = _format_player_meta(u["position"], u["mlb_team"])
                player_label = (
                    f"{u['name']} ({player_meta})" if player_meta else u["name"]
                )
                lines.append(
                    f"  {player_label} - {_format_owner_label(u)}"
                )
            lines.append("")

        if not r_players:
            lines.append("目前聯盟沒有 R 約球員。")
            lines.append("")

        lines.append(f"API 取得 {len(prospects)} 名 prospect 資料")

        message = "\n".join(lines)

        success, error = send_line_group_message(message)
        if success:
            print(f"[ProspectUpdate] LINE notification sent. "
                  f"Matched: {len(matched)}, Unmatched: {len(unmatched)}")
        else:
            print(f"[ProspectUpdate] LINE send failed: {error}")

    except Exception as e:
        print(f"[ProspectUpdate] Error: {e}")


def start_scheduler():
    """Start the background scheduler.

    Jobs:
    1. Keeper reminder: optional daily cron during keeper period
    2. Rookie call-up monitor: optional daily cron during MLB season
    3. Daily AR-Rank + season stats refresh: 18:00 during MLB season (single pass)
    4. Daily player status update + optional injury notification: during MLB season
    5. Daily transaction fetch: daily during MLB season
    6. Daily roster + snapshot + ownership sync: 00:30 Taiwan time (merged)
    7. Weekly war report: Monday 21:00 during MLB season
    8. Monthly war report: 1st of each month 20:45 during MLB season
    9. Prospect ranking update: optional Aug 15 LINE push
    """
    global _scheduler

    # Determine reminder mode
    if KEEPER_REMINDER_START:
        mode = "legacy"
        period_desc = f"{KEEPER_REMINDER_START} ~ {KEEPER_REMINDER_END or 'no end'}"
    else:
        mode = "annual"
        period_desc = f"every year {REMINDER_MONTH}/{REMINDER_START_DAY} ~ {REMINDER_MONTH}/{REMINDER_END_DAY}"

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
    except ImportError:
        print("[Scheduler] apscheduler not installed, scheduler disabled.")
        return

    _scheduler = BackgroundScheduler()

    # Job 1: Keeper reminders
    if KEEPER_REMINDER_ENABLED:
        _scheduler.add_job(
            _daily_reminder_job,
            CronTrigger(hour=REMINDER_CRON_HOUR, timezone=REMINDER_CRON_TZ),
            id="keeper_reminder",
            replace_existing=True,
        )

    # Job 2: Rookie call-up monitor
    if ROOKIE_MONITOR_ENABLED:
        _scheduler.add_job(
            _daily_rookie_monitor_job,
            CronTrigger(hour=REMINDER_CRON_HOUR, timezone=REMINDER_CRON_TZ),
            id="rookie_monitor",
            replace_existing=True,
        )

    # Job 3: Daily AR-Rank + season stats refresh
    # 18:00 Taiwan = 6:00 AM ET — after all US games end + Yahoo stats processed
    _scheduler.add_job(
        _daily_ar_rank_refresh_job,
        CronTrigger(
            hour=18,
            minute=0,
            timezone=REMINDER_CRON_TZ,
        ),
        id="ar_rank_refresh",
        replace_existing=True,
    )

    # Job 4: Daily player status update (IL/DTD/NA/O)
    _scheduler.add_job(
        _daily_player_status_job,
        CronTrigger(
            hour=REMINDER_CRON_HOUR,
            minute=30,
            timezone=REMINDER_CRON_TZ,
        ),
        id="player_status_update",
        replace_existing=True,
    )

    # Job 5: Daily transaction fetch (during MLB season)
    _scheduler.add_job(
        _daily_transaction_fetch_job,
        CronTrigger(
            hour=DAILY_SYNC_HOUR,
            minute=15,
            timezone=REMINDER_CRON_TZ,
        ),
        id="transaction_fetch",
        replace_existing=True,
    )

    # Job 6: Daily roster fetch + snapshot rebuild + ownership sync
    # (merged: the separate 00:30 ownership sync was duplicating these 16 roster fetches)
    _scheduler.add_job(
        _daily_roster_snapshot_rebuild_job,
        CronTrigger(
            hour=DAILY_SYNC_HOUR,
            minute=30,
            timezone=REMINDER_CRON_TZ,
        ),
        id="roster_snapshot_rebuild",
        replace_existing=True,
    )

    # Job 7: Weekly war report (Monday 21:00 - 3hr buffer after 18:00 AR-Rank refresh)
    _scheduler.add_job(
        _weekly_war_report_job,
        CronTrigger(
            day_of_week="mon",
            hour=21,
            minute=0,
            timezone=REMINDER_CRON_TZ,
        ),
        id="war_report",
        replace_existing=True,
    )

    # Job 8: Monthly war report (1st of each month at 20:45)
    _scheduler.add_job(
        _monthly_war_report_job,
        CronTrigger(
            day=1,
            hour=20,
            minute=45,
            timezone=REMINDER_CRON_TZ,
        ),
        id="monthly_report",
        replace_existing=True,
    )

    _scheduler.start()
    print(f"[Scheduler] Started ({mode} mode). "
          f"Check daily at {REMINDER_CRON_HOUR}:00 {REMINDER_CRON_TZ}")
    if KEEPER_REMINDER_ENABLED:
        print(f"[Scheduler] Keeper reminders every {REMINDER_INTERVAL_DAYS} days "
              f"(period: {period_desc})")
    else:
        print(f"[Scheduler] Keeper reminders disabled (period would be {period_desc})")
    if ROOKIE_MONITOR_ENABLED:
        print(f"[Scheduler] Rookie monitor active "
              f"(months {ROOKIE_MONITOR_START_MONTH}-{ROOKIE_MONITOR_END_MONTH})")
    else:
        print("[Scheduler] Rookie immediate LINE monitor disabled")
    print("[Scheduler] Daily AR-Rank + stats refresh: 18:00")
    if INJURY_LINE_ENABLED:
        print("[Scheduler] Daily player status update + injury digest: 12:30 PM")
    else:
        print("[Scheduler] Daily player status update: 12:30 PM (injury LINE disabled)")
    print(f"[Scheduler] Daily transaction fetch: {DAILY_SYNC_HOUR}:15 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Daily roster + snapshot + ownership sync: {DAILY_SYNC_HOUR}:30 {REMINDER_CRON_TZ}")
    print("[Scheduler] Weekly war report: every Monday 21:00")
    # Job 10: Annual prospect ranking update (Aug 15)
    if PROSPECT_UPDATE_LINE_ENABLED:
        _scheduler.add_job(
            _prospect_ranking_update_job,
            CronTrigger(
                month=8,
                day=15,
                hour=19,
                timezone=REMINDER_CRON_TZ,
            ),
            id="prospect_update",
            replace_existing=True,
        )

    print("[Scheduler] Monthly war report: 1st of each month 20:45")
    if PROSPECT_UPDATE_LINE_ENABLED:
        print("[Scheduler] Prospect ranking update: Aug 15 19:00")
    else:
        print("[Scheduler] Prospect ranking update disabled")

    # One-off test push: today's MLB games preview.
    # Fires 2026-04-22 01:10 Taiwan time then never again (DateTrigger is
    # idempotent after the time passes — safe to keep in code).
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZI
        tz = _ZI(REMINDER_CRON_TZ)
        run_at = _dt(2026, 4, 22, 1, 10, 0, tzinfo=tz)
        if run_at > _dt.now(tz):
            _scheduler.add_job(
                _daily_games_preview_job,
                DateTrigger(run_date=run_at),
                id="one_off_games_preview_20260422_0110",
                replace_existing=True,
            )
            print(f"[Scheduler] One-off games preview scheduled: {run_at}")
        else:
            print(f"[Scheduler] One-off games preview skipped (already past: {run_at})")
    except Exception as e:
        print(f"[Scheduler] One-off games preview registration failed: {e}")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
