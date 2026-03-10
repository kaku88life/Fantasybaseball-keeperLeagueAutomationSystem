"""
Keeper deadline reminder logic.
Determines which teams need reminders and sends emails.
"""
from __future__ import annotations

import os

from api.database import (
    get_all_submissions,
    get_all_teams,
    get_db,
    get_recent_notifications,
    insert_notification_log,
    _fetchall,
)
from src.notification.email_service import send_email

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3001")


def get_pending_teams(year: int) -> list[dict]:
    """Find teams that haven't submitted keeper selections, with manager email."""
    all_teams = get_all_teams()
    submissions = get_all_submissions(year)
    submitted_ids = {s["team_id"] for s in submissions}

    pending = []
    for t in all_teams:
        if t["id"] in submitted_ids:
            continue

        # Look up manager email from users table
        conn = get_db()
        try:
            users = _fetchall(
                conn,
                "SELECT yahoo_email FROM users WHERE team_id = %s",
                (t["id"],),
            )
        finally:
            conn.close()

        email = None
        for u in users:
            if u.get("yahoo_email"):
                email = u["yahoo_email"]
                break

        pending.append({
            "id": t["id"],
            "manager_name": t["manager_name"],
            "email": email,
            "has_email": email is not None,
        })

    return pending


def send_reminders(
    year: int,
    sent_by: str = "commissioner",
    cooldown_hours: int = 24,
) -> dict:
    """
    Send keeper reminder emails to all pending teams.
    Returns { sent: [], skipped: [], failed: [], no_email: [] }
    """
    pending = get_pending_teams(year)
    results: dict[str, list] = {
        "sent": [],
        "skipped": [],
        "failed": [],
        "no_email": [],
    }

    for team in pending:
        if not team["has_email"]:
            results["no_email"].append(team["manager_name"])
            insert_notification_log(
                year=year,
                team_id=team["id"],
                notification_type="keeper_reminder",
                channel="email",
                recipient_email="",
                sent_by=sent_by,
                status="skipped",
                error_message="No email address",
            )
            continue

        # Check cooldown
        recent = get_recent_notifications(
            year, team["id"], "keeper_reminder", cooldown_hours
        )
        if recent:
            results["skipped"].append(team["manager_name"])
            continue

        # Send email
        subject = f"[5-Man Keeper League] {year} 留用名單催繳提醒 Keeper Reminder"
        body = build_reminder_html(team, year)
        success, error = send_email(team["email"], subject, body)

        insert_notification_log(
            year=year,
            team_id=team["id"],
            notification_type="keeper_reminder",
            channel="email",
            recipient_email=team["email"],
            sent_by=sent_by,
            status="sent" if success else "failed",
            error_message=error,
        )

        if success:
            results["sent"].append(team["manager_name"])
        else:
            results["failed"].append({
                "manager": team["manager_name"],
                "error": error,
            })

    return results


def build_reminder_html(team_info: dict, year: int) -> str:
    """Build reminder email HTML content (bilingual zh-TW + English)."""
    # Ensure FRONTEND_URL has https:// prefix for production
    frontend = FRONTEND_URL
    if frontend and not frontend.startswith("http"):
        frontend = f"https://{frontend}"

    team_url = f"{frontend}/{year}/{team_info['id']}"
    manager = team_info["manager_name"]

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #4F46E5; margin-bottom: 16px;">
            5-Man Keeper League - {year} 留用名單催繳
        </h2>

        <p>Hi {manager},</p>

        <p>
            提醒您尚未繳交 {year} 年度的留用名單。<br>
            This is a reminder that your {year} keeper list has not been submitted yet.
        </p>

        <div style="background: #F3F4F6; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0 0 12px 0; font-weight: 600;">
                請點擊以下連結前往填寫：
            </p>
            <a href="{team_url}"
               style="display: inline-block; background: #4F46E5; color: white;
                      padding: 10px 24px; border-radius: 6px; text-decoration: none;
                      font-weight: 500;">
                前往留用頁面 Go to Keeper Page
            </a>
        </div>

        <p style="color: #6B7280; font-size: 14px;">
            如有任何問題，請聯繫 Commissioner。<br>
            If you have questions, please contact the Commissioner.
        </p>

        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;">
        <p style="color: #9CA3AF; font-size: 12px;">
            This email was sent by the 5-Man Keeper League system.
        </p>
    </div>
    """
