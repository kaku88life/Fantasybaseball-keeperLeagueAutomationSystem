"""
APScheduler-based keeper reminder scheduler.
Runs inside the FastAPI process during keeper selection period.
Sends LINE group reminders every N days (default: 3) at configured hour.
"""
from __future__ import annotations

import os
from datetime import datetime

KEEPER_REMINDER_START = os.getenv("KEEPER_REMINDER_START", "")
KEEPER_REMINDER_END = os.getenv("KEEPER_REMINDER_END", "")
REMINDER_CRON_HOUR = int(os.getenv("REMINDER_CRON_HOUR", "12"))
REMINDER_CRON_TZ = os.getenv("REMINDER_CRON_TZ", "Asia/Taipei")
REMINDER_INTERVAL_DAYS = int(os.getenv("REMINDER_INTERVAL_DAYS", "3"))

_scheduler = None


def _daily_reminder_job():
    """Daily job: send reminders if within the configured date range."""
    today = datetime.now().strftime("%Y-%m-%d")

    if KEEPER_REMINDER_START and today < KEEPER_REMINDER_START:
        print(f"[Scheduler] Not yet in reminder period (start: {KEEPER_REMINDER_START})")
        return
    if KEEPER_REMINDER_END and today > KEEPER_REMINDER_END:
        print(f"[Scheduler] Past reminder period (end: {KEEPER_REMINDER_END})")
        return

    year = datetime.now().year
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
    """Start the background scheduler. No-op if KEEPER_REMINDER_START is not set."""
    global _scheduler

    if not KEEPER_REMINDER_START:
        print("[Scheduler] KEEPER_REMINDER_START not set, scheduler disabled.")
        return

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
    print(f"[Scheduler] Started. Reminder check daily at {REMINDER_CRON_HOUR}:00 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Sends every {REMINDER_INTERVAL_DAYS} days "
          f"(period: {KEEPER_REMINDER_START} ~ {KEEPER_REMINDER_END or 'no end'})")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
