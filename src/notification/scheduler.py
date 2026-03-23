"""
APScheduler-based background scheduler.

Jobs:
1. Keeper reminder: LINE group reminders every N days during keeper period.
2. Rookie call-up monitor: daily check for R-contract player MLB debuts.
3. Weekly ranking refresh: every Monday during MLB season.
4. Daily player status update: IL/DTD/NA/O status during MLB season.
5. Monthly transaction fetch: Yahoo transactions on 1st of each month.

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


def _monthly_transaction_fetch_job():
    """Monthly job: fetch latest transactions from Yahoo API."""
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


def start_scheduler():
    """Start the background scheduler.

    Jobs:
    1. Keeper reminder: daily cron during keeper period
    2. Rookie call-up monitor: daily cron during MLB season
    3. Weekly ranking refresh: every Monday during MLB season
    4. Daily player status update: during MLB season
    5. Monthly transaction fetch: 1st of each month during season
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

    # Job 5: Monthly transaction fetch (1st of each month)
    _scheduler.add_job(
        _monthly_transaction_fetch_job,
        CronTrigger(
            day=1,
            hour=REMINDER_CRON_HOUR,
            timezone=REMINDER_CRON_TZ,
        ),
        id="transaction_fetch",
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
    print("[Scheduler] Monthly transaction fetch: 1st of each month")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
