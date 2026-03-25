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
DAILY_SYNC_HOUR = int(os.getenv("DAILY_SYNC_HOUR", "13"))         # 1 PM Taiwan = ~midnight US EST

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
    """Daily job: update player IL/DTD/NA/O status from Yahoo API."""
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

        # Fetch top 500 players for status updates (lighter than full ranking)
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

    except Exception as e:
        print(f"[StatusUpdate] Error: {e}")


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


def start_scheduler():
    """Start the background scheduler.

    Jobs:
    1. Keeper reminder: daily cron during keeper period
    2. Rookie call-up monitor: daily cron during MLB season
    3. Weekly ranking refresh: every Monday during MLB season
    4. Daily player status update: during MLB season
    5. Daily transaction fetch: daily during MLB season
    6. Season start notification: LINE message on Opening Day
    7. Daily roster ownership sync: fetch rosters, update owner_manager
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

    # Job 3: Weekly ranking refresh (every Monday at noon)
    _scheduler.add_job(
        _weekly_ranking_refresh_job,
        CronTrigger(
            day_of_week="mon",
            hour=REMINDER_CRON_HOUR,
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

    _scheduler.start()
    print(f"[Scheduler] Started ({mode} mode). "
          f"Check daily at {REMINDER_CRON_HOUR}:00 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Keeper reminders every {REMINDER_INTERVAL_DAYS} days "
          f"(period: {period_desc})")
    if ROOKIE_MONITOR_ENABLED:
        print(f"[Scheduler] Rookie monitor active "
              f"(months {ROOKIE_MONITOR_START_MONTH}-{ROOKIE_MONITOR_END_MONTH})")
    print("[Scheduler] Weekly ranking refresh: every Monday")
    print("[Scheduler] Daily player status update: 12:30 PM")
    print(f"[Scheduler] Daily transaction fetch: {DAILY_SYNC_HOUR}:15 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Season start notification: {DAILY_SYNC_HOUR}:00 {REMINDER_CRON_TZ} "
          f"(Opening Day: {SEASON_START_DATE})")
    print(f"[Scheduler] Daily roster ownership sync: {DAILY_SYNC_HOUR}:30 {REMINDER_CRON_TZ}")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
