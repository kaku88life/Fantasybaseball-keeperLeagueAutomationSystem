"""
APScheduler-based background scheduler.

Jobs:
1. Keeper reminder: LINE group reminders every N days during keeper period.
2. Rookie call-up monitor: daily check for R-contract player MLB debuts.
3. Weekly ranking refresh: every Monday during MLB season.
4. Daily player status update: IL/DTD/NA/O status during MLB season.
5. Daily transaction fetch: Yahoo transactions during MLB season.
6. Season start notification: LINE message on Opening Day (US midnight).
7. Daily roster ownership sync: fetch team rosters, update owner_manager (US midnight).

Yearly auto-mode: set REMINDER_MONTH / REMINDER_START_DAY / REMINDER_END_DAY
to define a fixed annual window (e.g. March 1-15 every year).
"""
from __future__ import annotations

import os
from datetime import datetime

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

# --- Rookie call-up monitoring ---
# Active during MLB season (April-September by default)
ROOKIE_MONITOR_ENABLED = os.getenv("ROOKIE_MONITOR_ENABLED", "true").lower() == "true"
ROOKIE_MONITOR_START_MONTH = int(os.getenv("ROOKIE_MONITOR_START_MONTH", "3"))
ROOKIE_MONITOR_END_MONTH = int(os.getenv("ROOKIE_MONITOR_END_MONTH", "9"))

# --- Season start notification + daily roster sync ---
# US midnight = 13:00 Taiwan time (UTC+8, EST is UTC-5; 0:00 EST = 05:00 UTC = 13:00 TWN)
# During DST (EDT, UTC-4): 0:00 EDT = 04:00 UTC = 12:00 TWN
# We use 13:00 TWN as a safe default (between the two offsets)
SEASON_START_DATE = os.getenv("SEASON_START_DATE", "2026-03-26")  # Opening Day date
DAILY_SYNC_HOUR = int(os.getenv("DAILY_SYNC_HOUR", "0"))           # midnight Taiwan time

_scheduler = None


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


def _weekly_ranking_refresh_job():
    """Weekly job: refresh Yahoo player rankings + status during MLB season."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[RankingRefresh] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[RankingRefresh] Refreshing player rankings for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import bulk_upsert_player_rankings, update_ar_ranks

        # Resolve league key
        from config.settings import get_league_key
        league_key = get_league_key(year)
        if not league_key:
            print(f"[RankingRefresh] No league key for year {year}")
            return

        # Fetch OR rankings (25 players per batch)
        import time
        all_players: list[dict] = []
        for start in range(0, 1500, 25):
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

                from api.routers.commissioner import _parse_yahoo_player, _parse_yahoo_stats
                batch_players = []
                for key, val in players_section.items():
                    if key == "count":
                        continue
                    if isinstance(val, dict) and "player" in val:
                        pdata = val["player"]
                        if isinstance(pdata, list) and len(pdata) >= 2:
                            player_info = _parse_yahoo_player(pdata[0])
                            stats_info = _parse_yahoo_stats(
                                pdata[1].get("player_stats", {}),
                                prefix="proj",
                            )
                            player_info.update(stats_info)
                            batch_players.append(player_info)

                if not batch_players:
                    break

                for i, p in enumerate(batch_players):
                    p["o_rank"] = start + i + 1

                all_players.extend(batch_players)
                time.sleep(1)

            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                else:
                    print(f"[RankingRefresh] Batch error at {start}: {e}")
                    break

        if all_players:
            bulk_upsert_player_rankings(year, all_players)
            print(f"[RankingRefresh] Updated {len(all_players)} player rankings for {year}")
        else:
            print("[RankingRefresh] No players fetched")

    except YahooTokenError as e:
        print(f"[RankingRefresh] Token error: {e}")
    except Exception as e:
        print(f"[RankingRefresh] Error: {e}")


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
        from api.database import get_db, get_player_statuses
        import time

        # Resolve league key
        from config.settings import get_league_key
        league_key = get_league_key(year)
        if not league_key:
            print(f"[StatusUpdate] No league key for year {year}")
            return

        # Step 1: Snapshot old statuses BEFORE update
        old_statuses = get_player_statuses(year)
        has_old_data = bool(old_statuses)

        # Step 2: Fetch and update statuses from Yahoo
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

        # Step 3: Detect changes and send LINE notification
        if has_old_data:
            _send_injury_change_notification(year, old_statuses)
        else:
            print("[StatusUpdate] First run (no previous data), skipping injury notification.")

    except Exception as e:
        print(f"[StatusUpdate] Error: {e}")


def _send_injury_change_notification(year: int, old_statuses: dict[str, dict]):
    """Compare old vs new player statuses and send LINE notification for changes."""
    from api.database import get_player_statuses
    from src.notification.line_service import send_line_group_message

    new_statuses = get_player_statuses(year)

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
        team = new_info.get("mlb_team", "")
        label = f"  {name} ({pos}/{team}) - {owner}" if pos else f"  {name} - {owner}"

        if (not old_status or old_status not in injury_statuses) and new_status in injury_statuses:
            new_injuries.append(f"{label} -> {new_status}")
        elif old_status in injury_statuses and (not new_status or new_status not in injury_statuses):
            recovered.append(f"{label} -> Active")
        elif old_status in injury_statuses and new_status in injury_statuses and old_status != new_status:
            status_changes.append(f"{label} -> {new_status} (was {old_status})")

    # Build message only if there are changes
    if not new_injuries and not recovered and not status_changes:
        print("[StatusUpdate] No injury status changes detected.")
        return

    lines = ["[5-Man Keeper League] 傷兵異動通知", ""]

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
        print(f"[StatusUpdate] LINE injury notification sent ({total} changes).")
    else:
        print(f"[StatusUpdate] LINE notification failed: {error}")


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

        # Load existing file and merge (dedup by transaction_id)
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tx_file = data_dir / f"yahoo_{year}_transactions.json"

        existing_tx = []
        if tx_file.exists():
            with open(tx_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            if isinstance(existing_data, dict):
                existing_tx = existing_data.get("transactions", [])
            elif isinstance(existing_data, list):
                existing_tx = existing_data

        # Dedup by transaction_id
        existing_ids = {tx.get("transaction_id") for tx in existing_tx}
        added = 0
        for tx in new_transactions:
            if tx.get("transaction_id") not in existing_ids:
                existing_tx.append(tx)
                added += 1

        # Save merged data
        save_data = {"transactions": existing_tx}
        with open(tx_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

        print(f"[TransactionFetch] {len(new_transactions)} total, "
              f"{added} new transactions added. "
              f"File: {tx_file.name} ({len(existing_tx)} total)")

    except Exception as e:
        print(f"[TransactionFetch] Error: {e}")


def _season_start_notification_job():
    """Daily job (at DAILY_SYNC_HOUR): send LINE notification on Opening Day."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if today_str != SEASON_START_DATE:
        return

    year = datetime.now().year
    print(f"[SeasonStart] Today is Opening Day ({today_str})! Sending LINE notification...")

    try:
        from src.notification.line_service import send_line_group_message
        message = (
            f"[5-Man Keeper League]\n"
            f"\u26be {year} 賽季正式開始！Play Ball! \u26be\n"
            f"祝各位 GM 本季順利，好球連發！"
        )
        success, error = send_line_group_message(message)
        if success:
            print(f"[SeasonStart] LINE notification sent for {year} Opening Day.")
        else:
            print(f"[SeasonStart] LINE notification failed: {error}")
    except Exception as e:
        print(f"[SeasonStart] Error sending notification: {e}")


def _daily_roster_ownership_sync_job():
    """Daily job (at DAILY_SYNC_HOUR): fetch Yahoo team rosters and sync owner_manager."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[RosterSync] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[RosterSync] Syncing roster ownership for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import sync_roster_ownership, get_all_teams
        from config.settings import get_league_key
        import time

        league_key = get_league_key(year)
        if not league_key:
            print(f"[RosterSync] No league key for year {year}")
            return

        # Get all teams from Yahoo to map team_key -> manager_name
        db_teams = get_all_teams()

        # Fetch all teams from Yahoo API
        teams_path = f"/league/{league_key}/teams"
        teams_data = yahoo_api_get(teams_path)
        league_section = teams_data.get("fantasy_content", {}).get("league", [])
        if len(league_section) < 2:
            print("[RosterSync] No teams data from Yahoo API")
            return

        teams_section = league_section[1].get("teams", {})
        team_count = teams_section.get("count", 0)

        # Map yahoo_team_id -> manager_name using DB
        yahoo_id_to_manager: dict[str, str] = {}
        for db_team in db_teams:
            if db_team.get("yahoo_team_id"):
                yahoo_id_to_manager[str(db_team["yahoo_team_id"])] = db_team["manager_name"]

        # Build ownership_map: player_key -> manager_name
        ownership_map: dict[str, str] = {}

        for i in range(team_count):
            team_entry = teams_section.get(str(i), {}).get("team", [])
            if not team_entry:
                continue

            # Extract yahoo team key and ID
            team_info_list = team_entry[0] if isinstance(team_entry, list) else []
            team_key = ""
            team_id_str = ""
            for item in team_info_list:
                if isinstance(item, dict):
                    if "team_key" in item:
                        team_key = item["team_key"]
                    if "team_id" in item:
                        team_id_str = str(item["team_id"])

            manager_name = yahoo_id_to_manager.get(team_id_str, "")
            if not manager_name:
                # Fallback: try manager name from Yahoo data
                managers_list = next(
                    (item["managers"] for item in team_info_list
                     if isinstance(item, dict) and "managers" in item),
                    []
                )
                if managers_list and isinstance(managers_list, list):
                    mgr = managers_list[0].get("manager", {})
                    manager_name = mgr.get("nickname", "")

            if not team_key:
                continue

            # Fetch this team's roster
            try:
                roster_path = f"/team/{team_key}/roster"
                roster_data = yahoo_api_get(roster_path)
                roster_section = (
                    roster_data.get("fantasy_content", {})
                    .get("team", [])
                )
                if len(roster_section) >= 2:
                    players_section = roster_section[1].get("roster", {}).get("players", {})
                    p_count = players_section.get("count", 0)
                    for j in range(p_count):
                        player_entry = players_section.get(str(j), {}).get("player", [])
                        if not player_entry:
                            continue
                        player_info_list = player_entry[0] if isinstance(player_entry, list) else []
                        player_key = ""
                        for item in player_info_list:
                            if isinstance(item, dict) and "player_key" in item:
                                player_key = item["player_key"]
                                break
                        if player_key and manager_name:
                            ownership_map[player_key] = manager_name
                time.sleep(0.6)
            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                else:
                    print(f"[RosterSync] Error fetching roster for team {team_key}: {e}")

        if ownership_map:
            sync_roster_ownership(year, ownership_map)
            print(f"[RosterSync] Ownership sync complete: {len(ownership_map)} players mapped.")
        else:
            print("[RosterSync] No ownership data fetched.")

    except YahooTokenError as e:
        print(f"[RosterSync] Token error: {e}")
    except Exception as e:
        print(f"[RosterSync] Error: {e}")


def _weekly_war_report_job():
    """Weekly job (Monday 18:45): generate and send weekly war report to LINE."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[WarReport] Off-season (month {month}), skipping.")
        return

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
            return

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
            return

        teams_section = league_standings[1].get("standings", [{}])[0].get("teams", {})
        team_count = teams_section.get("count", 0)

        from api.routers.commissioner import _parse_yahoo_player

        current_standings: list[dict] = []
        for i in range(team_count):
            team_raw = teams_section.get(str(i), {}).get("team", [])
            if not team_raw:
                continue
            # Parse team info
            info_list = team_raw[0] if isinstance(team_raw, list) else []
            team_name = ""
            manager_name = ""
            for item in info_list:
                if isinstance(item, dict):
                    if "name" in item:
                        team_name = item["name"]
                    if "managers" in item:
                        mgrs = item["managers"]
                        if isinstance(mgrs, list) and mgrs:
                            manager_name = mgrs[0].get("manager", {}).get("nickname", "")
            # Parse standings
            standing = {}
            if len(team_raw) > 1:
                standing = team_raw[1].get("team_standings", {})
            rank = int(standing.get("rank", 0))
            record = standing.get("outcome_totals", {})
            wins = int(record.get("wins", 0))
            losses = int(record.get("losses", 0))
            ties = int(record.get("ties", 0))

            current_standings.append({
                "team_name": team_name,
                "manager_name": manager_name,
                "rank": rank,
                "wins": wins,
                "losses": losses,
                "ties": ties,
            })

        current_standings.sort(key=lambda x: x["rank"])

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

        # --- 4. Fetch top 5 hitters and pitchers by Yahoo Points ---
        time.sleep(1)
        top_batters: list[dict] = []
        top_pitchers: list[dict] = []

        for pos_type, result_list in [("B", top_batters), ("P", top_pitchers)]:
            try:
                players_path = (
                    f"/league/{league_key}/players"
                    f";sort=PTS;sort_type=week;sort_week={report_week}"
                    f";position={pos_type};count=5;out=stats,ownership"
                )
                pdata = yahoo_api_get(players_path)
                p_league = pdata.get("fantasy_content", {}).get("league", [])
                if len(p_league) >= 2:
                    p_section = p_league[1].get("players", {})
                    for pk_idx in range(p_section.get("count", 0)):
                        p_entry = p_section.get(str(pk_idx), {}).get("player", [])
                        if not p_entry or not isinstance(p_entry, list):
                            continue
                        # Parse player info
                        p_info = {}
                        for item in (p_entry[0] if isinstance(p_entry[0], list) else [p_entry[0]]):
                            if isinstance(item, dict):
                                if "name" in item:
                                    p_info["name"] = item["name"].get("full", "")
                                if "display_position" in item:
                                    p_info["position"] = item["display_position"]
                                if "editorial_team_abbr" in item:
                                    p_info["mlb_team"] = item["editorial_team_abbr"]
                                if "ownership" in item:
                                    owner = item["ownership"]
                                    p_info["owner_team"] = owner.get("owner_team_name", "FA")
                        # Parse points
                        pts = 0.0
                        if len(p_entry) > 1:
                            player_pts = p_entry[1].get("player_points", {})
                            try:
                                pts = float(player_pts.get("total", 0))
                            except (ValueError, TypeError):
                                pts = 0.0
                        p_info["points"] = pts
                        result_list.append(p_info)
                time.sleep(1)
            except Exception as e:
                print(f"[WarReport] Error fetching top {pos_type} players: {e}")

        # --- 5. Build LINE message ---
        lines = [f"[5-Man Keeper League] 第 {report_week} 週戰報", ""]

        # Standings
        lines.append("-- 排名 --")
        for s in current_standings:
            w, l, t = s["wins"], s["losses"], s["ties"]
            mgr = s["manager_name"]
            rank = s["rank"]
            # Rank change indicator
            prev_rank = prev_rank_map.get(mgr)
            if prev_rank is not None and prev_rank != rank:
                diff = prev_rank - rank  # positive = improved
                change = f" ^{diff}" if diff > 0 else f" v{-diff}"
            else:
                change = " --"
            lines.append(f"{rank}. {mgr} ({w}-{l}-{t}){change}")
        lines.append("")

        # Matchup results
        if matchups:
            lines.append("-- 本週對戰 --")
            for m in matchups:
                t1, t2 = m[0], m[1]
                p1, p2 = t1["points"], t2["points"]
                m1, m2 = t1["manager"] or t1["name"], t2["manager"] or t2["name"]
                w1 = " W" if t1["is_winner"] else ""
                w2 = " W" if t2["is_winner"] else ""
                lines.append(f"{m1} {p1:.0f}{w1} - {p2:.0f}{w2} {m2}")
            lines.append("")

        # Top batters
        if top_batters:
            lines.append("-- 本週最佳打者 (Yahoo Pts) --")
            for idx, b in enumerate(top_batters[:5], 1):
                name = b.get("name", "?")
                pos = b.get("position", "")
                pts = b.get("points", 0)
                owner = b.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        # Top pitchers
        if top_pitchers:
            lines.append("-- 本週最佳投手 (Yahoo Pts) --")
            for idx, p in enumerate(top_pitchers[:5], 1):
                name = p.get("name", "?")
                pos = p.get("position", "")
                pts = p.get("points", 0)
                owner = p.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        lines.append("* Yahoo Fantasy Points (僅供參考)")

        message = "\n".join(lines)

        # Send LINE message
        success, error = send_line_group_message(message)
        if success:
            print(f"[WarReport] Week {report_week} war report sent to LINE.")
        else:
            print(f"[WarReport] LINE send failed: {error}")

    except YahooTokenError as e:
        print(f"[WarReport] Token error: {e}")
    except Exception as e:
        print(f"[WarReport] Error: {e}")


def _monthly_war_report_job():
    """Monthly job (1st of each month, 19:00): generate monthly summary report."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (April-October; skips March since no full month data yet)
    if month < 4 or month > 10:
        print(f"[MonthlyReport] Off-season or too early (month {month}), skipping.")
        return

    year = now.year
    report_month = month - 1  # Report covers the previous month
    month_names = {3: "3月", 4: "4月", 5: "5月", 6: "6月",
                   7: "7月", 8: "8月", 9: "9月", 10: "10月"}
    month_label = month_names.get(report_month, f"{report_month}月")

    print(f"[MonthlyReport] Generating {month_label} report for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_weekly_standings
        from src.notification.line_service import send_line_group_message
        from config.settings import get_league_key
        import time
        import json
        from pathlib import Path

        league_key = get_league_key(year)
        if not league_key:
            print(f"[MonthlyReport] No league key for year {year}")
            return

        # --- 1. Get current week to determine which weeks belong to the report month ---
        meta_path = f"/league/{league_key}/metadata"
        meta_data = yahoo_api_get(meta_path)
        league_meta = meta_data.get("fantasy_content", {}).get("league", [])
        current_week = 1
        start_date_str = ""
        if isinstance(league_meta, list):
            for item in league_meta:
                if isinstance(item, dict):
                    if "current_week" in item:
                        current_week = int(item["current_week"])
                    if "start_date" in item:
                        start_date_str = item["start_date"]

        # Estimate which weeks fall in the report month
        # Yahoo seasons typically start late March; each week is 7 days
        # We use the weekly_standings table to find weeks with data in the report month
        report_week_end = current_week - 1  # Last completed week

        # --- 2. Fetch current standings for month-end snapshot ---
        time.sleep(1)
        standings_path = f"/league/{league_key}/standings"
        standings_data = yahoo_api_get(standings_path)
        league_standings = standings_data.get("fantasy_content", {}).get("league", [])
        if len(league_standings) < 2:
            print("[MonthlyReport] No standings data.")
            return

        teams_section = league_standings[1].get("standings", [{}])[0].get("teams", {})
        team_count = teams_section.get("count", 0)

        current_standings: list[dict] = []
        for i in range(team_count):
            team_raw = teams_section.get(str(i), {}).get("team", [])
            if not team_raw:
                continue
            info_list = team_raw[0] if isinstance(team_raw, list) else []
            team_name = ""
            manager_name = ""
            for item in info_list:
                if isinstance(item, dict):
                    if "name" in item:
                        team_name = item["name"]
                    if "managers" in item:
                        mgrs = item["managers"]
                        if isinstance(mgrs, list) and mgrs:
                            manager_name = mgrs[0].get("manager", {}).get("nickname", "")
            standing = {}
            if len(team_raw) > 1:
                standing = team_raw[1].get("team_standings", {})
            rank = int(standing.get("rank", 0))
            record = standing.get("outcome_totals", {})
            wins = int(record.get("wins", 0))
            losses = int(record.get("losses", 0))
            ties = int(record.get("ties", 0))
            current_standings.append({
                "team_name": team_name,
                "manager_name": manager_name,
                "rank": rank,
                "wins": wins,
                "losses": losses,
                "ties": ties,
            })
        current_standings.sort(key=lambda x: x["rank"])

        # Find the earliest week of the report month from weekly_standings
        # We look for the week saved ~4 weeks ago as start-of-month reference
        month_start_week = max(report_week_end - 4, 1)
        prev_month_standings = get_weekly_standings(year, month_start_week)
        prev_rank_map = {s["manager_name"]: s["rank"] for s in prev_month_standings}
        # Also compute W-L changes (monthly record)
        prev_record_map = {
            s["manager_name"]: (s.get("wins", 0), s.get("losses", 0), s.get("ties", 0))
            for s in prev_month_standings
        }

        # --- 3. Monthly matchup summary (aggregate all weeks in the month) ---
        time.sleep(1)
        team_monthly_record: dict[str, dict] = {}  # manager -> {w, l, t}
        for wk in range(month_start_week + 1, report_week_end + 1):
            try:
                sb_path = f"/league/{league_key}/scoreboard;week={wk}"
                sb_data = yahoo_api_get(sb_path)
                sb_league = sb_data.get("fantasy_content", {}).get("league", [])
                if len(sb_league) < 2:
                    continue
                sb = sb_league[1].get("scoreboard", {})
                matchups_section = None
                if "0" in sb and "matchups" in sb["0"]:
                    matchups_section = sb["0"]["matchups"]
                elif "matchups" in sb:
                    matchups_section = sb["matchups"]
                if not matchups_section:
                    continue

                m_count = matchups_section.get("count", 0)
                for mi in range(m_count):
                    m_raw = matchups_section.get(str(mi), {}).get("matchup", {})
                    teams_data = m_raw.get("0", {}).get("teams", {})
                    winner_key = m_raw.get("winner_team_key", "")
                    t_count = teams_data.get("count", 0)

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
                        pts = 0.0
                        if len(t_raw) > 1:
                            tp = t_raw[1].get("team_points", {})
                            try:
                                pts = float(tp.get("total", 0))
                            except (ValueError, TypeError):
                                pass
                        match_info.append({"key": t_key, "mgr": t_mgr, "pts": pts})

                    if len(match_info) == 2:
                        for mi_t in match_info:
                            mgr = mi_t["mgr"]
                            if mgr not in team_monthly_record:
                                team_monthly_record[mgr] = {"w": 0, "l": 0, "t": 0}
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

        # --- 4. Top 5 hitters and pitchers (month stats) ---
        time.sleep(1)
        top_batters: list[dict] = []
        top_pitchers: list[dict] = []

        for pos_type, result_list in [("B", top_batters), ("P", top_pitchers)]:
            try:
                # Use season sort_type=lastmonth if available, otherwise season
                players_path = (
                    f"/league/{league_key}/players"
                    f";sort=PTS;sort_type=lastmonth"
                    f";position={pos_type};count=5;out=stats,ownership"
                )
                pdata = yahoo_api_get(players_path)
                p_league = pdata.get("fantasy_content", {}).get("league", [])
                if len(p_league) >= 2:
                    p_section = p_league[1].get("players", {})
                    for pk_idx in range(p_section.get("count", 0)):
                        p_entry = p_section.get(str(pk_idx), {}).get("player", [])
                        if not p_entry or not isinstance(p_entry, list):
                            continue
                        p_info = {}
                        for item in (p_entry[0] if isinstance(p_entry[0], list) else [p_entry[0]]):
                            if isinstance(item, dict):
                                if "name" in item:
                                    p_info["name"] = item["name"].get("full", "")
                                if "display_position" in item:
                                    p_info["position"] = item["display_position"]
                                if "editorial_team_abbr" in item:
                                    p_info["mlb_team"] = item["editorial_team_abbr"]
                                if "ownership" in item:
                                    owner = item["ownership"]
                                    p_info["owner_team"] = owner.get("owner_team_name", "FA")
                        pts = 0.0
                        if len(p_entry) > 1:
                            player_pts = p_entry[1].get("player_points", {})
                            try:
                                pts = float(player_pts.get("total", 0))
                            except (ValueError, TypeError):
                                pts = 0.0
                        p_info["points"] = pts
                        result_list.append(p_info)
                time.sleep(1)
            except Exception as e:
                print(f"[MonthlyReport] Error fetching top {pos_type}: {e}")

        # --- 5. Transaction summary from JSON file ---
        tx_summary: list[str] = []
        try:
            data_dir = Path(__file__).resolve().parent.parent.parent / "data"
            tx_file = data_dir / f"yahoo_{year}_transactions.json"
            if tx_file.exists():
                with open(tx_file, "r", encoding="utf-8") as f:
                    tx_data = json.load(f)
                all_tx = tx_data.get("transactions", [])

                # Filter transactions from the report month
                month_trades = 0
                month_adds = 0
                month_drops = 0
                notable_trades: list[str] = []

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
                        # Collect notable trade details (first 3)
                        if len(notable_trades) < 3:
                            players = tx.get("players", [])
                            names = [p.get("name", "?") for p in players[:4]]
                            notable_trades.append(", ".join(names))
                    elif tx_type in ("add", "add/drop"):
                        month_adds += 1
                        if "drop" in tx_type:
                            month_drops += 1
                    elif tx_type == "drop":
                        month_drops += 1

                if month_trades or month_adds or month_drops:
                    tx_summary.append(f"交易: {month_trades} 筆 | 撿人: {month_adds} 筆 | 釋出: {month_drops} 筆")
                    for nt in notable_trades:
                        tx_summary.append(f"  Trade: {nt}")
        except Exception as e:
            print(f"[MonthlyReport] Transaction summary error: {e}")

        # --- 6. Build LINE message ---
        lines = [f"[5-Man Keeper League] {year} {month_label}月報", ""]

        # Standings with monthly rank change
        lines.append("-- 排名 --")
        for s in current_standings:
            w, l, t = s["wins"], s["losses"], s["ties"]
            mgr = s["manager_name"]
            rank = s["rank"]
            prev_rank = prev_rank_map.get(mgr)
            if prev_rank is not None and prev_rank != rank:
                diff = prev_rank - rank
                change = f" ^{diff}" if diff > 0 else f" v{-diff}"
            else:
                change = " --"
            lines.append(f"{rank}. {mgr} ({w}-{l}-{t}){change}")
        lines.append("")

        # Monthly team records
        if team_monthly_record:
            lines.append(f"-- {month_label}戰績 --")
            sorted_monthly = sorted(
                team_monthly_record.items(),
                key=lambda x: (x[1]["w"], -x[1]["l"]),
                reverse=True,
            )
            for mgr, rec in sorted_monthly:
                lines.append(f"{mgr}: {rec['w']}-{rec['l']}-{rec['t']}")
            lines.append("")

        # Top batters
        if top_batters:
            lines.append(f"-- {month_label}最佳打者 (Yahoo Pts) --")
            for idx, b in enumerate(top_batters[:5], 1):
                name = b.get("name", "?")
                pos = b.get("position", "")
                pts = b.get("points", 0)
                owner = b.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        # Top pitchers
        if top_pitchers:
            lines.append(f"-- {month_label}最佳投手 (Yahoo Pts) --")
            for idx, p in enumerate(top_pitchers[:5], 1):
                name = p.get("name", "?")
                pos = p.get("position", "")
                pts = p.get("points", 0)
                owner = p.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        # Transaction summary
        if tx_summary:
            lines.append(f"-- {month_label}交易摘要 --")
            lines.extend(tx_summary)
            lines.append("")

        lines.append("* Yahoo Fantasy Points (僅供參考)")

        message = "\n".join(lines)

        success, error = send_line_group_message(message)
        if success:
            print(f"[MonthlyReport] {month_label} report sent to LINE.")
        else:
            print(f"[MonthlyReport] LINE send failed: {error}")

    except YahooTokenError as e:
        print(f"[MonthlyReport] Token error: {e}")
    except Exception as e:
        print(f"[MonthlyReport] Error: {e}")


def start_scheduler():
    """Start the background scheduler.

    Jobs:
    1. Keeper reminder: daily cron during keeper period
    2. Rookie call-up monitor: daily cron during MLB season
    3. Weekly ranking refresh: every Monday 18:00 during MLB season
    4. Daily player status update + injury notification: during MLB season
    5. Daily transaction fetch: daily during MLB season
    6. Season start notification: LINE message on Opening Day
    7. Daily roster ownership sync: fetch rosters, update owner_manager
    8. Weekly war report: every Monday 18:45 during MLB season
    9. Monthly war report: 1st of each month 19:00 during MLB season
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
    except ImportError:
        print("[Scheduler] apscheduler not installed, scheduler disabled.")
        return

    _scheduler = BackgroundScheduler()

    # Job 1: Keeper reminders
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

    # Job 3: Weekly ranking refresh (every Monday at 18:00 - after Yahoo settles stats)
    _scheduler.add_job(
        _weekly_ranking_refresh_job,
        CronTrigger(
            day_of_week="mon",
            hour=18,
            timezone=REMINDER_CRON_TZ,
        ),
        id="ranking_refresh",
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

    # Job 6: Season start notification (Opening Day LINE message)
    _scheduler.add_job(
        _season_start_notification_job,
        CronTrigger(
            hour=DAILY_SYNC_HOUR,
            minute=0,
            timezone=REMINDER_CRON_TZ,
        ),
        id="season_start_notification",
        replace_existing=True,
    )

    # Job 7: Daily roster ownership sync (US midnight = DAILY_SYNC_HOUR Taiwan)
    _scheduler.add_job(
        _daily_roster_ownership_sync_job,
        CronTrigger(
            hour=DAILY_SYNC_HOUR,
            minute=30,
            timezone=REMINDER_CRON_TZ,
        ),
        id="roster_ownership_sync",
        replace_existing=True,
    )

    # Job 8: Weekly war report (every Monday at 18:45 - after ranking refresh)
    _scheduler.add_job(
        _weekly_war_report_job,
        CronTrigger(
            day_of_week="mon",
            hour=18,
            minute=45,
            timezone=REMINDER_CRON_TZ,
        ),
        id="war_report",
        replace_existing=True,
    )

    # Job 9: Monthly war report (1st of each month at 19:00)
    _scheduler.add_job(
        _monthly_war_report_job,
        CronTrigger(
            day=1,
            hour=19,
            timezone=REMINDER_CRON_TZ,
        ),
        id="monthly_report",
        replace_existing=True,
    )

    _scheduler.start()
    print(f"[Scheduler] Started ({mode} mode). "
          f"Check daily at {REMINDER_CRON_HOUR}:00 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Keeper reminders every {REMINDER_INTERVAL_DAYS} days "
          f"(period: {period_desc})")
    if ROOKIE_MONITOR_ENABLED:
        print(f"[Scheduler] Rookie monitor active "
              f"(months {ROOKIE_MONITOR_START_MONTH}-{ROOKIE_MONITOR_END_MONTH})")
    print("[Scheduler] Weekly ranking refresh: every Monday 18:00")
    print("[Scheduler] Daily player status update + injury notification: 12:30 PM")
    print(f"[Scheduler] Daily transaction fetch: {DAILY_SYNC_HOUR}:15 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Season start notification: {DAILY_SYNC_HOUR}:00 {REMINDER_CRON_TZ} "
          f"(Opening Day: {SEASON_START_DATE})")
    print(f"[Scheduler] Daily roster ownership sync: {DAILY_SYNC_HOUR}:30 {REMINDER_CRON_TZ}")
    print("[Scheduler] Weekly war report: every Monday 18:45")
    print("[Scheduler] Monthly war report: 1st of each month 19:00")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
