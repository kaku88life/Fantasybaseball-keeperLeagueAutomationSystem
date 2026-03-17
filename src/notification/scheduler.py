"""
APScheduler-based keeper reminder scheduler.
Runs inside the FastAPI process during keeper selection period.
Sends LINE group reminders every N days (default: 3) at configured hour.

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


def start_scheduler():
    """Start the background scheduler.

    Enabled when either:
    - KEEPER_REMINDER_START is set (legacy explicit range), or
    - REMINDER_MONTH/START_DAY/END_DAY are set (annual window, enabled by default)
    """
    global _scheduler

    # Determine mode
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
    _scheduler.add_job(
        _daily_reminder_job,
        CronTrigger(hour=REMINDER_CRON_HOUR, timezone=REMINDER_CRON_TZ),
        id="keeper_reminder",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[Scheduler] Started ({mode} mode). "
          f"Check daily at {REMINDER_CRON_HOUR}:00 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Sends every {REMINDER_INTERVAL_DAYS} days "
          f"(period: {period_desc})")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
