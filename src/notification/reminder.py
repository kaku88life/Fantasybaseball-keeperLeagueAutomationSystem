"""
Keeper deadline reminder logic.
Sends a single LINE group message listing all pending teams.
"""
from __future__ import annotations

import os

from api.database import (
    get_all_submissions,
    get_all_teams,
    get_recent_notifications,
    insert_notification_log,
)
from src.notification.line_service import send_line_group_message

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3001")


def get_pending_teams(year: int) -> list[dict]:
    """Find teams that haven't submitted keeper selections."""
    all_teams = get_all_teams()
    submissions = get_all_submissions(year)
    submitted_ids = {s["team_id"] for s in submissions}

    pending = []
    for t in all_teams:
        if t["id"] in submitted_ids:
            continue
        pending.append({
            "id": t["id"],
            "manager_name": t["manager_name"],
        })

    return pending


def send_reminders(
    year: int,
    sent_by: str = "commissioner",
    cooldown_hours: int = 24,
) -> dict:
    """
    Send a single LINE group reminder listing all pending teams.
    Returns { sent_to_group, pending_managers, skipped_reason, error }.
    """
    pending = get_pending_teams(year)

    if not pending:
        return {
            "sent_to_group": False,
            "pending_managers": [],
            "skipped_reason": "all_submitted",
            "error": None,
        }

    # Cooldown: check if a LINE group reminder was sent recently
    # Use team_id=0 as sentinel for "group message" (not per-team)
    recent = get_recent_notifications(
        year, team_id=0, notification_type="keeper_reminder_line", hours=cooldown_hours
    )
    if recent:
        return {
            "sent_to_group": False,
            "pending_managers": [t["manager_name"] for t in pending],
            "skipped_reason": "cooldown",
            "error": None,
        }

    # Build group message and send
    message = build_reminder_text(pending, year)
    success, error = send_line_group_message(message)

    # Log the send (one entry for the group send, team_id=0)
    insert_notification_log(
        year=year,
        team_id=0,
        notification_type="keeper_reminder_line",
        channel="line",
        recipient_email="",
        sent_by=sent_by,
        status="sent" if success else "failed",
        error_message=error,
    )

    return {
        "sent_to_group": success,
        "pending_managers": [t["manager_name"] for t in pending],
        "skipped_reason": None,
        "error": error if not success else None,
    }


def build_reminder_text(pending_teams: list[dict], year: int) -> str:
    """Build plain text reminder for LINE group (bilingual zh-TW + English)."""
    frontend = FRONTEND_URL
    if frontend and not frontend.startswith("http"):
        frontend = f"https://{frontend}"

    manager_list = "\n".join(
        f"  - {t['manager_name']}" for t in pending_teams
    )

    return (
        f"[5-Man Keeper League] {year} 留用名單催繳\n"
        f"Keeper List Reminder\n"
        f"\n"
        f"以下 {len(pending_teams)} 支隊伍尚未繳交：\n"
        f"The following {len(pending_teams)} team(s) have not submitted:\n"
        f"\n"
        f"{manager_list}\n"
        f"\n"
        f"請前往填寫 Go to:\n"
        f"{frontend}/{year}"
    )
