"""
Fantasy Baseball Keeper League - Commissioner Admin Routes
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.database import (
    approve_submission,
    bulk_upsert_player_rankings,
    create_buyout,
    delete_buyout,
    delete_submission,
    delete_yahoo_token,
    get_all_buyouts,
    get_all_submissions,
    get_all_teams,
    get_ranking_fetch_status,
    get_team_by_id,
    get_team_buyouts,
    get_user_by_id,
    save_snapshot,
    update_ar_ranks,
    update_buyout,
    update_last_season_stats,
    update_team_adjustments,
    upsert_team,
)
from api.dependencies import get_current_commissioner
from api.schemas import (
    ApproveRequest,
    AssignTeamRequest,
    BuyoutCreateRequest,
    BuyoutUpdateRequest,
    ImportExcelResponse,
    SubmissionStatusSchema,
    TeamAdjustmentsRequest,
)
from api.serializers import league_state_to_dict

router = APIRouter()


@router.post("/import-excel", response_model=ImportExcelResponse)
async def import_excel(
    file: UploadFile = File(...),
    year: int = 2025,
    user: dict = Depends(get_current_commissioner),
):
    """
    Import an Excel file and create a league snapshot.
    Commissioner only.
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx or .xlsm file")

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Import using existing parser
        from scripts.import_excel import import_yearly_sheet, load_workbook

        wb = load_workbook(tmp_path)
        sheet_name = f"{year}年選秀前名單"

        if sheet_name not in wb.sheetnames:
            available = [s for s in wb.sheetnames if "選秀" in s]
            raise HTTPException(
                status_code=400,
                detail=f"Sheet '{sheet_name}' not found. Available: {available}",
            )

        teams = import_yearly_sheet(wb[sheet_name], year)

        # Calculate salary cap for the year
        from config.settings import FAAB_BASE, get_salary_cap
        salary_cap = get_salary_cap(year)

        for t in teams:
            if not t.salary_cap:
                t.salary_cap = salary_cap
            if not t.faab_budget:
                t.faab_budget = FAAB_BASE

        # Build LeagueState
        from src.contract.models import LeagueState
        ls = LeagueState(year=year, teams=teams)

        # Save to database
        data = league_state_to_dict(ls)
        save_snapshot(year, data, source_file=file.filename, imported_by=user["id"])

        # Ensure teams exist in teams table
        for t in teams:
            upsert_team(
                manager_name=t.manager_name,
                team_name=t.team_name,
                yahoo_team_id=t.yahoo_team_id or "",
            )

        return ImportExcelResponse(
            year=year,
            teams_count=len(teams),
            teams=[t.manager_name for t in teams],
            message=f"Successfully imported {len(teams)} teams for {year}",
        )
    finally:
        os.unlink(tmp_path)


@router.get("/submissions/{year}", response_model=list[SubmissionStatusSchema])
async def get_submission_status(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get submission status for all teams in a year."""
    try:
        all_teams = get_all_teams()
        submissions = get_all_submissions(year)
    except Exception as e:
        print(f"[COMMISSIONER ERROR] submissions/{year} DB query failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    sub_map = {s["team_id"]: s for s in submissions}
    print(f"[COMMISSIONER] submissions/{year}: teams={len(all_teams)}, submissions={len(submissions)}", flush=True)

    result = []
    for t in all_teams:
        sub = sub_map.get(t["id"])
        result.append(SubmissionStatusSchema(
            team_id=t["id"],
            manager_name=t["manager_name"],
            team_name=t.get("team_name", ""),
            is_submitted=sub is not None,
            submitted_at=sub.get("submitted_at") if sub else None,
            is_valid=bool(sub["is_valid"]) if sub else False,
            commissioner_approved=bool(sub["commissioner_approved"]) if sub else False,
            commissioner_notes=sub.get("commissioner_notes") or "" if sub else "",
        ))

    return result


@router.get("/submissions/{year}/{team_id}")
async def get_submission_detail(
    year: int,
    team_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get detailed submission for a specific team."""
    from api.database import get_submission
    sub = get_submission(year, team_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No submission found")

    team = get_team_by_id(team_id)
    return {
        "team_id": team_id,
        "manager_name": team["manager_name"] if team else "",
        "team_name": team["team_name"] if team else "",
        **sub,
    }


@router.post("/approve/{year}/{team_id}")
async def approve_team_submission(
    year: int,
    team_id: int,
    body: ApproveRequest,
    user: dict = Depends(get_current_commissioner),
):
    """Approve or reject a team's keeper submission.
    Reject = auto-unlock (deletes submission, preserves selections).
    """
    from api.database import get_submission
    sub = get_submission(year, team_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No submission found")

    if body.approved:
        approve_submission(year, team_id, True, body.notes)
        return {"message": "Submission approved", "year": year, "team_id": team_id}
    else:
        # Reject = auto-unlock: delete submission so user can re-edit
        delete_submission(year, team_id)
        return {"message": "Submission rejected and unlocked", "year": year, "team_id": team_id}


@router.post("/assign-team")
async def assign_user_to_team(
    body: AssignTeamRequest,
    user: dict = Depends(get_current_commissioner),
):
    """Manually assign a user to a team."""
    from api.database import get_db

    target_user = get_user_by_id(body.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    team = get_team_by_id(body.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET team_id = %s WHERE id = %s",
                (body.team_id, body.user_id),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "message": f"User {target_user['yahoo_nickname']} assigned to team {team['manager_name']}",
    }


@router.get("/users")
async def list_users(user: dict = Depends(get_current_commissioner)):
    """List all registered users with their team assignments."""
    from api.database import get_db, _fetchall

    try:
        conn = get_db()
    except Exception as e:
        print(f"[COMMISSIONER ERROR] users DB connect failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Database connection error: {e}")

    try:
        rows = _fetchall(
            conn,
            """SELECT u.id, u.yahoo_guid, u.yahoo_nickname, u.yahoo_email,
                      u.team_id, u.is_commissioner, u.last_login,
                      u.line_name, t.manager_name, t.team_name
               FROM users u
               LEFT JOIN teams t ON u.team_id = t.id
               ORDER BY u.yahoo_nickname""",
        )
        return rows
    except Exception as e:
        print(f"[COMMISSIONER ERROR] users query failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Database query error: {e}")
    finally:
        conn.close()


@router.put("/users/{user_id}/line-name")
async def update_user_line_name_admin(
    user_id: int,
    body: dict,
    user: dict = Depends(get_current_commissioner),
):
    """Update or clear a user's LINE name. Commissioner only."""
    from api.database import get_db

    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    new_name = (body.get("line_name") or "").strip()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET line_name = %s WHERE id = %s",
                (new_name if new_name else None, user_id),
            )
        conn.commit()
    finally:
        conn.close()

    action = f"updated to '{new_name}'" if new_name else "cleared"
    return {"message": f"LINE name {action} for user #{user_id}"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Delete a user account. Commissioner only. Cannot delete yourself."""
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    from api.database import get_db
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()

    nickname = target.get("yahoo_nickname") or f"#{user_id}"
    return {"message": f"User {nickname} deleted"}


@router.post("/set-commissioner/{user_id}")
async def set_commissioner(
    user_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Grant commissioner role to a user. Commissioner only."""
    from api.database import get_db

    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET is_commissioner = 1 WHERE id = %s", (user_id,)
            )
        conn.commit()
    finally:
        conn.close()

    return {"message": f"User {target['yahoo_nickname']} is now commissioner"}


@router.post("/unlock/{year}/{team_id}")
async def unlock_submission(
    year: int,
    team_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Unlock a team's submission so they can re-edit. Keeper selections are preserved."""
    from api.database import get_submission

    sub = get_submission(year, team_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No submission found")

    delete_submission(year, team_id)
    team = get_team_by_id(team_id)
    manager = team["manager_name"] if team else f"team {team_id}"
    return {"message": f"Submission unlocked for {manager}", "year": year, "team_id": team_id}


@router.delete("/keeper-selections/{year}/{team_id}")
async def clear_keeper_selections(
    year: int,
    team_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Clear all keeper selections for a team in a year. Commissioner only.
    Also removes any submission record so the team starts fresh."""
    from api.database import delete_keeper_selections, get_submission

    team = get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Remove submission if exists
    sub = get_submission(year, team_id)
    if sub:
        delete_submission(year, team_id)

    # Remove all selections
    delete_keeper_selections(year, team_id)

    manager = team["manager_name"]
    return {
        "message": f"All keeper selections cleared for {manager} ({year})",
        "year": year,
        "team_id": team_id,
    }


@router.get("/team-adjustments/{team_id}")
async def get_team_adjustments(
    team_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get trade compensation and FAAB adjustment for a team."""
    team = get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {
        "team_id": team_id,
        "manager_name": team["manager_name"],
        "trade_compensation": team.get("trade_compensation", 0) or 0,
        "faab_adjustment": team.get("faab_adjustment", 0) or 0,
    }


@router.get("/all-team-adjustments")
async def get_all_team_adjustments(
    user: dict = Depends(get_current_commissioner),
):
    """Get trade compensation and FAAB adjustments for all teams."""
    teams = get_all_teams()
    return [
        {
            "team_id": t["id"],
            "manager_name": t["manager_name"],
            "trade_compensation": t.get("trade_compensation", 0) or 0,
            "faab_adjustment": t.get("faab_adjustment", 0) or 0,
        }
        for t in teams
    ]


@router.put("/team-adjustments/{team_id}")
async def update_team_adjustments_endpoint(
    team_id: int,
    body: TeamAdjustmentsRequest,
    user: dict = Depends(get_current_commissioner),
):
    """Update trade compensation and FAAB adjustment for a team. Commissioner only."""
    team = get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    update_team_adjustments(team_id, body.trade_compensation, body.faab_adjustment)
    return {
        "message": f"Adjustments updated for {team['manager_name']}",
        "team_id": team_id,
        "trade_compensation": body.trade_compensation,
        "faab_adjustment": body.faab_adjustment,
    }


# ========== Keeper Reminders ==========

@router.post("/reminders/{year}/send")
async def send_keeper_reminders(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Send LINE group reminder to all teams that haven't submitted. Commissioner only."""
    from src.notification.reminder import send_reminders
    result = send_reminders(year, sent_by="commissioner", cooldown_hours=1)
    return result


@router.get("/reminders/{year}/status")
async def get_reminder_status(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get reminder notification history for a year."""
    from api.database import get_reminder_history
    history = get_reminder_history(year)
    # psycopg2 RealDictCursor returns datetime objects;
    # FastAPI's jsonable_encoder handles them automatically via .isoformat()
    return {"year": year, "history": history}


@router.get("/reminders/{year}/pending")
async def get_pending_teams_endpoint(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get list of teams that haven't submitted keeper lists."""
    from src.notification.reminder import get_pending_teams
    pending = get_pending_teams(year)
    return {"year": year, "pending_count": len(pending), "teams": pending}


@router.post("/line/test")
async def test_line_connection_endpoint(
    user: dict = Depends(get_current_commissioner),
):
    """Test LINE Bot group connection by sending a test message. Commissioner only."""
    from src.notification.line_service import test_line_connection
    return test_line_connection()


@router.post("/line/test-push")
async def test_line_push_endpoint(
    payload: dict,
    user: dict = Depends(get_current_commissioner),
):
    """Send a test LINE push message to an arbitrary target ID (user/group/room).

    Body: {"target_id": "U...", "message": "optional custom text"}

    The LINE Bot must already be added as a friend (for user IDs) or be a
    member of the target group/room for the push to succeed.
    """
    from src.notification.line_format import center_line, divider_line, report_width
    from src.notification.line_service import send_line_push_message

    target_id = (payload.get("target_id") or "").strip()
    message = (payload.get("message") or "").strip()

    if not target_id:
        raise HTTPException(status_code=400, detail="target_id is required")

    if not message:
        width = report_width()
        message = "\n".join([
            divider_line(width),
            center_line("5-Man Keeper League", width),
            center_line("LINE push test OK", width),
            divider_line(width),
            "",
            "Target:",
            f"{target_id[:6]}...{target_id[-4:]}",
        ])

    success, error = send_line_push_message(target_id, message)
    return {
        "success": success,
        "message": "Push message sent" if success else error,
        "target_id_preview": f"{target_id[:6]}...{target_id[-4:]}",
    }


@router.post("/line/test-reminder")
async def test_line_reminder_endpoint(
    payload: dict,
    user: dict = Depends(get_current_commissioner),
):
    """Preview the actual keeper-reminder message by pushing it to an admin.

    Uses the real reminder template (same as the scheduled group push) but
    sends to a single target — useful for verifying wording/URL before the
    group blast.

    Body: {"target_id"?: "U...", "year"?: 2026}
    - target_id defaults to env LINE_ADMIN_USER_ID
    - year defaults to current calendar year

    Does NOT write notification_log and does NOT respect cooldown (it's a test).
    """
    import os
    from datetime import datetime

    from src.notification.line_format import center_line, divider_line, report_width
    from src.notification.line_service import send_line_push_message
    from src.notification.reminder import build_reminder_text, get_pending_teams

    target_id = (payload.get("target_id") or "").strip()
    if not target_id:
        target_id = (os.getenv("LINE_ADMIN_USER_ID") or "").strip()
    if not target_id:
        raise HTTPException(
            status_code=400,
            detail="target_id not provided and LINE_ADMIN_USER_ID env var not set",
        )

    year = payload.get("year") or datetime.now().year
    pending = get_pending_teams(int(year))

    if not pending:
        width = report_width()
        message = "\n".join([
            divider_line(width),
            center_line("5-Man Keeper League", width),
            center_line(f"{year} 留用催繳預覽", width),
            center_line("Reminder Preview", width),
            divider_line(width),
            "",
            "所有隊伍已完成提交。",
            "No reminder would be sent.",
        ])
    else:
        message = build_reminder_text(pending, int(year))

    success, error = send_line_push_message(target_id, message)
    return {
        "success": success,
        "message": "Reminder preview sent" if success else error,
        "target_id_preview": f"{target_id[:6]}...{target_id[-4:]}",
        "year": int(year),
        "pending_count": len(pending),
        "pending_managers": [t["manager_name"] for t in pending],
    }


@router.post("/statcast/sync")
async def trigger_statcast_sync(
    background_tasks: BackgroundTasks,
    days: int = 20,
    async_mode: bool = True,
    user: dict = Depends(get_current_commissioner),
):
    """Ingest recent Statcast days (backfills gaps). Commissioner only.

    Defaults to background execution — a cold backfill is ~8s per day fetched.
    """
    from src.notification.scheduler import _daily_statcast_sync_job

    if not async_mode:
        return _daily_statcast_sync_job()

    background_tasks.add_task(_daily_statcast_sync_job)
    return {
        "success": True,
        "status": "scheduled",
        "message": f"Statcast sync dispatched (up to {days} days). Check coverage in ~1-3 min.",
    }


@router.get("/league-keys")
async def get_league_keys_endpoint(user: dict = Depends(get_current_commissioner)):
    """Resolved Yahoo league keys per season, plus this season's status.

    Surfaces the failure mode where a new season has no key and every
    Yahoo-dependent job goes quiet.
    """
    from datetime import date as _date

    from api.database import get_all_league_keys
    from api.yahoo_service import resolve_league_key

    current_year = _date.today().year
    try:
        cached = get_all_league_keys()
    except Exception as e:
        cached = []
        print(f"[CommissionerAPI] league key cache read failed: {e}")

    current_key = resolve_league_key(current_year, allow_discovery=False)
    return {
        "current_year": current_year,
        "current_league_key": current_key,
        "current_resolved": bool(current_key),
        "cached": [
            {
                "year": row["year"],
                "league_key": row["league_key"],
                "source": row["source"],
                "resolved_at": (
                    row["resolved_at"].isoformat() if row.get("resolved_at") else None
                ),
            }
            for row in cached
        ],
    }


@router.get("/scheduler/status")
async def scheduler_status_endpoint(
    limit: int = 50,
    job_id: str = "",
    user: dict = Depends(get_current_commissioner),
):
    """Live scheduler state + recent job outcomes.

    This is the answer to "did the weekly report even fire?" — `jobs` shows the
    next scheduled run, `recent_runs` shows what actually happened.
    """
    from api.database import get_recent_job_runs
    from src.notification.scheduler import get_scheduler_status

    status = get_scheduler_status()
    try:
        runs = get_recent_job_runs(limit=limit, job_id=job_id)
    except Exception as e:
        runs = []
        status["recent_runs_error"] = str(e)

    return {
        **status,
        "recent_runs": [
            {
                "job_id": r["job_id"],
                "status": r["status"],
                "detail": r["detail"],
                "recorded_at": (
                    r["recorded_at"].isoformat() if r.get("recorded_at") else None
                ),
            }
            for r in runs
        ],
    }


class TriggerWarReportRequest(BaseModel):
    target_id: Optional[str] = None   # None => scheduled behavior (LINE group)
    dry_run: bool = False              # True => skip LINE, return text only
    async_mode: bool = False            # True => dispatch in BackgroundTasks


@router.post("/line/trigger-war-report")
async def trigger_war_report_endpoint(
    background_tasks: BackgroundTasks,
    payload: TriggerWarReportRequest | None = None,
    user: dict = Depends(get_current_commissioner),
):
    """Manually fire the weekly war report job.

    dry_run=true is kept synchronous so the caller can inspect the rendered
    text. target/group push modes run synchronously by default so the
    Commissioner UI can show the actual LINE push result. async_mode=true can
    still dispatch to BackgroundTasks when immediate return is preferred.
    """
    from src.notification.scheduler import _weekly_war_report_job

    target_id = (payload.target_id if payload else None) or ""
    dry_run = bool(payload.dry_run if payload else False)
    async_mode = bool(payload.async_mode if payload else False)
    mode = "target" if target_id else "group"

    if dry_run:
        try:
            result = _weekly_war_report_job(target_id=target_id, dry_run=True)
            return {**result, "status": "completed", "mode": "dry_run"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"War report failed: {e}")

    if not async_mode:
        result = _weekly_war_report_job(target_id=target_id, dry_run=False)
        return {**result, "status": "completed", "mode": mode}

    def _run_bg(tid: str) -> None:
        try:
            _weekly_war_report_job(target_id=tid, dry_run=False)
        except Exception as e:
            print(f"[CommissionerAPI] Background war report failed: {e}")

    background_tasks.add_task(_run_bg, target_id)
    return {
        "success": True,
        "status": "scheduled",
        "mode": mode,
        "message": "War report dispatched in background. Check LINE in 30-90s.",
    }


@router.post("/line/trigger-monthly-report")
async def trigger_monthly_report_endpoint(
    background_tasks: BackgroundTasks,
    payload: TriggerWarReportRequest | None = None,
    user: dict = Depends(get_current_commissioner),
):
    """Manually fire the monthly war report job.

    Mirrors trigger-war-report: dry_run=true is synchronous (returns rendered
    text); target/group modes run synchronously by default and can opt into
    BackgroundTasks with async_mode=true.
    """
    from src.notification.scheduler import _monthly_war_report_job

    target_id = (payload.target_id if payload else None) or ""
    dry_run = bool(payload.dry_run if payload else False)
    async_mode = bool(payload.async_mode if payload else False)
    mode = "target" if target_id else "group"

    if dry_run:
        try:
            result = _monthly_war_report_job(target_id=target_id, dry_run=True)
            return {**result, "status": "completed", "mode": "dry_run"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Monthly report failed: {e}")

    if not async_mode:
        result = _monthly_war_report_job(target_id=target_id, dry_run=False)
        return {**result, "status": "completed", "mode": mode}

    def _run_bg(tid: str) -> None:
        try:
            _monthly_war_report_job(target_id=tid, dry_run=False)
        except Exception as e:
            print(f"[CommissionerAPI] Background monthly report failed: {e}")

    background_tasks.add_task(_run_bg, target_id)
    return {
        "success": True,
        "status": "scheduled",
        "mode": mode,
        "message": "Monthly report dispatched in background. Check LINE in 30-90s.",
    }


@router.post("/line/trigger-injury-digest")
async def trigger_injury_digest_endpoint(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_commissioner),
):
    """Manually fire the daily player status job.

    Runs in the background because the full roster scan across 16 teams
    easily exceeds the client timeout. LINE injury digest is sent only when
    INJURY_LINE_ENABLED is enabled in the backend environment.
    """
    from src.notification.scheduler import _daily_player_status_job

    def _run_bg() -> None:
        try:
            _daily_player_status_job()
        except Exception as e:
            print(f"[CommissionerAPI] Background injury digest failed: {e}")

    background_tasks.add_task(_run_bg)
    return {
        "success": True,
        "status": "scheduled",
        "message": "Injury status update dispatched in background. Check Zeabur logs in 30-90s.",
    }


@router.post("/refresh-transactions")
async def refresh_transactions_endpoint(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_commissioner),
):
    """Manually fire the daily transaction fetch job (paginated, overwrites file).

    The scheduled job runs at 00:15 Taiwan time. Use this endpoint right after
    a deploy to immediately refresh FAAB / trade / add-drop data on the
    container's filesystem, so analytics pages (draft stats, pickup counts)
    show up-to-date numbers without waiting for the nightly cron.

    Runs in background because a full-season paginated fetch can take 30-60s.
    """
    from src.notification.scheduler import _daily_transaction_fetch_job

    def _run_bg() -> None:
        try:
            _daily_transaction_fetch_job()
        except Exception as e:
            print(f"[CommissionerAPI] Background transaction refresh failed: {e}")

    background_tasks.add_task(_run_bg)
    return {
        "success": True,
        "status": "scheduled",
        "message": (
            "Transaction fetch dispatched. Stats should update in 30-90s; "
            "check Zeabur logs for [TransactionFetch] output."
        ),
    }


# ========== Buyout Management ==========

@router.get("/buyouts/{year}")
async def list_all_buyouts(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get all active buyout records for a year. Commissioner only."""
    buyouts = get_all_buyouts(year)
    return {"year": year, "buyouts": buyouts, "total_count": len(buyouts)}


@router.get("/buyouts/{year}/{team_id}")
async def list_team_buyouts(
    year: int,
    team_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get buyout records for a specific team. Commissioner only."""
    team = get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    buyouts = get_team_buyouts(team_id, year)
    return {
        "year": year,
        "team_id": team_id,
        "manager_name": team["manager_name"],
        "buyouts": buyouts,
    }


@router.post("/buyouts")
async def create_buyout_record(
    body: BuyoutCreateRequest,
    user: dict = Depends(get_current_commissioner),
):
    """Create a new buyout record. Commissioner only."""
    team = get_team_by_id(body.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    result = create_buyout(
        team_id=body.team_id,
        year=body.year,
        player_name=body.player_name,
        original_contract=body.original_contract,
        buyout_salary=body.buyout_salary,
        buyout_faab=body.buyout_faab,
        buyout_years=body.buyout_years,
        remaining_years=body.remaining_years,
        buyout_type=body.buyout_type,
        use_faab=body.use_faab,
        notes=body.notes,
    )
    return {
        "message": f"Buyout created for {body.player_name} ({team['manager_name']})",
        "buyout": result,
    }


@router.put("/buyouts/{buyout_id}")
async def update_buyout_record(
    buyout_id: int,
    body: BuyoutUpdateRequest,
    user: dict = Depends(get_current_commissioner),
):
    """Update a buyout record. Commissioner only."""
    updates = body.model_dump(exclude_none=True)
    result = update_buyout(buyout_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Buyout record not found")
    return {"message": "Buyout updated", "buyout": result}


@router.delete("/buyouts/{buyout_id}")
async def delete_buyout_record(
    buyout_id: int,
    user: dict = Depends(get_current_commissioner),
):
    """Delete a buyout record. Commissioner only."""
    delete_buyout(buyout_id)
    return {"message": f"Buyout #{buyout_id} deleted"}


# ========== Yahoo API Token Management ==========

@router.get("/yahoo-token/status")
async def get_yahoo_token_status(
    user: dict = Depends(get_current_commissioner),
):
    """Get Yahoo API token connection status. Commissioner only."""
    from api.yahoo_service import get_token_status
    return get_token_status()


@router.post("/yahoo-token/refresh")
async def refresh_yahoo_token(
    user: dict = Depends(get_current_commissioner),
):
    """Manually trigger Yahoo token refresh. Commissioner only."""
    from api.yahoo_service import YahooTokenError, refresh_db_token
    from api.database import get_commissioner_yahoo_token

    token_row = get_commissioner_yahoo_token()
    if not token_row:
        raise HTTPException(
            status_code=404,
            detail="No Yahoo token found. Please log in via Yahoo OAuth first.",
        )

    try:
        refresh_db_token(token_row)
        from api.yahoo_service import get_token_status
        return get_token_status()
    except YahooTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/yahoo-token/test")
async def test_yahoo_connection(
    user: dict = Depends(get_current_commissioner),
):
    """Test Yahoo API connection with current token. Commissioner only."""
    from api.yahoo_service import YahooTokenError, yahoo_api_get

    try:
        yahoo_api_get("/users;use_login=1/profile")
        return {"status": "ok", "message": "Yahoo API 連線正常 Connection working"}
    except YahooTokenError as e:
        return {"status": "error", "message": f"Token error: {e}"}
    except RuntimeError as e:
        return {"status": "error", "message": f"API error: {e}"}


@router.delete("/yahoo-token")
async def disconnect_yahoo_token(
    user: dict = Depends(get_current_commissioner),
):
    """Disconnect Yahoo API (delete stored token). Commissioner only."""
    delete_yahoo_token(user["id"])
    return {"message": "Yahoo API token disconnected"}


@router.get("/yahoo-debug/raw")
async def yahoo_debug_raw(
    path: str,
    user: dict = Depends(get_current_commissioner),
):
    """Debug: proxy a raw Yahoo Fantasy API GET and return the JSON.

    Example: /api/commissioner/yahoo-debug/raw?path=/league/469.l.80910/standings
    Commissioner only. Use to inspect Yahoo response shapes when parsing breaks.
    """
    from api.yahoo_service import YahooTokenError, yahoo_api_get

    if not path.startswith("/"):
        path = "/" + path
    try:
        return yahoo_api_get(path)
    except YahooTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ========== Player Rankings (Yahoo API Fetch) ==========

# Import centralized Yahoo keys from config (single source of truth)
from config.settings import YAHOO_GAME_KEYS as _YAHOO_GAME_KEYS, YAHOO_LEAGUE_NUMS as _YAHOO_LEAGUE_NUMS

# Yahoo stat_id -> our column name mapping
# Verified from league settings API: /league/{key}/settings -> stat_categories
# Hitting stats
_HITTING_STAT_MAP: dict[str, str] = {
    "7": "r",       # Runs (stat_id=7)
    "8": "h",       # Hits
    "12": "hr",     # Home Runs
    "13": "rbi",    # RBI
    "16": "sb",     # Stolen Bases
    "3": "avg",     # Batting Average
    "55": "ops",    # OPS
}

# Pitching stats
_PITCHING_STAT_MAP: dict[str, str] = {
    "28": "w",      # Wins
    "32": "sv",     # Saves
    "48": "hld",    # Holds
    "42": "k",      # Strikeouts
    "26": "era",    # ERA
    "27": "whip",   # WHIP
    "83": "qs",     # Quality Starts (stat_id=83)
}


def _resolve_league_key(year: int) -> str:
    """Build Yahoo league key from year and env YAHOO_LEAGUE_ID."""
    game_key = _YAHOO_GAME_KEYS.get(year)
    if not game_key:
        raise HTTPException(
            status_code=400,
            detail=f"No Yahoo game key configured for year {year}",
        )
    league_id = os.getenv("YAHOO_LEAGUE_ID", "")
    if not league_id:
        raise HTTPException(
            status_code=400,
            detail="YAHOO_LEAGUE_ID environment variable not set",
        )
    # league_id might be full "469.l.80910" or just "80910"
    league_num = league_id.split(".")[-1] if "." in league_id else league_id
    return f"{game_key}.l.{league_num}"


def _parse_yahoo_player(player_data: list) -> dict:
    """Parse a single Yahoo player entry from the nested API response.

    Yahoo Fantasy API returns players as a list where:
    - Index 0: player_key info
    - Index 1: player name info
    - etc.
    The structure varies, so we iterate and look for specific keys.
    """
    result = {
        "player_key": "",
        "player_name": "",
        "position": "",
        "mlb_team": "",
        "o_rank": None,
        "ar_rank": None,
        "status": None,
    }

    # player_data is a list of dicts with various info
    for item in player_data:
        if isinstance(item, dict):
            if "player_key" in item:
                result["player_key"] = item["player_key"]
            if "name" in item:
                name_info = item["name"]
                full = name_info.get("full", "")
                if full:
                    result["player_name"] = full
            if "editorial_team_abbr" in item:
                result["mlb_team"] = item["editorial_team_abbr"].upper()
            if "display_position" in item:
                result["position"] = item["display_position"]
            if "primary_position" in item and not result["position"]:
                result["position"] = item["primary_position"]
            if "status" in item:
                result["status"] = item["status"]
            # Eligible positions list
            if "eligible_positions" in item:
                pass  # use display_position instead
        elif isinstance(item, list):
            # Sometimes nested lists contain position info
            for sub in item:
                if isinstance(sub, dict):
                    if "position" in sub and sub.get("position_type"):
                        pass  # skip position sub-items

    return result


def _parse_yahoo_stats(stats_data: dict, prefix: str = "stat") -> dict:
    """Parse Yahoo stats coverage into our flat stat dict.

    Args:
        stats_data: The stats section from Yahoo API
        prefix: "stat" for actual stats, "proj" for projections
    """
    result = {}
    stats_list = stats_data.get("stats", [])

    for stat_entry in stats_list:
        stat = stat_entry.get("stat", {})
        stat_id = str(stat.get("stat_id", ""))
        value = stat.get("value", "")

        if value == "" or value == "-":
            continue

        # stat_id 60 = H/AB (e.g. "179/541") — extract AB from denominator
        if stat_id == "60" and "/" in str(value):
            try:
                ab_str = str(value).split("/")[1]
                result[f"{prefix}_ab"] = int(float(ab_str))
            except (ValueError, TypeError, IndexError):
                pass
            continue

        # stat_id 50 = IP (Innings Pitched, e.g. "195.1")
        if stat_id == "50":
            try:
                result[f"{prefix}_ip"] = float(value)
            except (ValueError, TypeError):
                pass
            continue

        # Check hitting stats
        if stat_id in _HITTING_STAT_MAP:
            col = _HITTING_STAT_MAP[stat_id]
            try:
                if col in ("avg", "ops"):
                    result[f"{prefix}_{col}"] = float(value)
                else:
                    result[f"{prefix}_{col}"] = int(float(value))
            except (ValueError, TypeError):
                pass

        # Check pitching stats
        if stat_id in _PITCHING_STAT_MAP:
            col = _PITCHING_STAT_MAP[stat_id]
            try:
                if col in ("era", "whip"):
                    result[f"{prefix}_{col}"] = float(value)
                else:
                    result[f"{prefix}_{col}"] = int(float(value))
            except (ValueError, TypeError):
                pass

    return result


def _fetch_yahoo_players_batch(
    league_key: str, sort: str, sort_type: str,
    max_players: int = 3000, batch_size: int = 25,
    stat_prefix: str = "stat",
) -> tuple[list[dict], list[str]]:
    """Fetch players from Yahoo API in batches with a given sort/sort_type.

    Returns (players_list, errors_list).
    """
    import time
    from api.yahoo_service import YahooTokenError, yahoo_api_get

    all_players: list[dict] = []
    errors: list[str] = []
    max_retries = 3

    for start in range(0, max_players, batch_size):
        try:
            # Build path with sort and sort_type params
            path = (
                f"/league/{league_key}/players"
                f";start={start};count={batch_size};sort={sort}"
                f";sort_type={sort_type};out=stats"
            )

            # Retry loop for 429 rate limit errors.
            # Long backoff (60s/120s/300s) because Yahoo bans are hours-long.
            data = None
            for attempt in range(max_retries):
                try:
                    data = yahoo_api_get(path)
                    break
                except RuntimeError as api_err:
                    if "429" in str(api_err):
                        wait = [60, 120, 300][attempt]
                        print(
                            f"[FetchRankings] Rate limited (429) at start={start}, "
                            f"retry {attempt + 1}/{max_retries} after {wait}s...",
                            flush=True,
                        )
                        time.sleep(wait)
                    else:
                        raise

            if data is None:
                errors.append(f"Batch start={start} sort={sort}: rate limited after {max_retries} retries")
                print(f"[FetchRankings] Giving up at start={start} after {max_retries} retries", flush=True)
                break

            # Parse the response
            fantasy_content = data.get("fantasy_content", {})
            league = fantasy_content.get("league", [])

            # League data is typically [meta_info, {players: {...}}]
            players_section = None
            for section in league:
                if isinstance(section, dict) and "players" in section:
                    players_section = section["players"]
                    break

            if not players_section:
                print(f"[FetchRankings] No players in batch start={start} (sort={sort})", flush=True)
                break

            # Parse each player
            batch_count = 0
            for key, val in players_section.items():
                if key == "count":
                    continue
                if not isinstance(val, dict) or "player" not in val:
                    continue

                player_raw = val["player"]
                if not isinstance(player_raw, list):
                    continue

                # Parse player info from first part (list of info dicts)
                player_info_list = player_raw[0] if player_raw else []
                player = _parse_yahoo_player(player_info_list)

                # Extract player_key from player info
                for item in player_info_list:
                    if isinstance(item, dict):
                        if "player_key" in item:
                            player["player_key"] = item["player_key"]

                # Parse stats (second part of player list)
                if len(player_raw) > 1:
                    stats_section = player_raw[1]
                    if isinstance(stats_section, dict):
                        player_stats = stats_section.get("player_stats", {})
                        if player_stats:
                            stats = _parse_yahoo_stats(player_stats, stat_prefix)
                            player.update(stats)

                # Rank is the position in sorted results
                player["_rank"] = start + batch_count + 1

                if player["player_key"] and player["player_name"]:
                    all_players.append(player)
                    batch_count += 1

            print(
                f"[FetchRankings] Batch start={start} sort={sort}: {batch_count} players parsed",
                flush=True,
            )

            if batch_count < batch_size:
                break

            # Rate limiting: 0.6s between requests (avoid Yahoo 429)
            time.sleep(0.6)

        except YahooTokenError as e:
            raise HTTPException(status_code=401, detail=f"Yahoo token error: {e}")
        except RuntimeError as e:
            errors.append(f"Batch start={start} sort={sort}: {e}")
            print(f"[FetchRankings] Error at start={start}: {e}", flush=True)
            if start == 0:
                raise HTTPException(status_code=502, detail=f"Yahoo API error: {e}")
            break
        except Exception as e:
            errors.append(f"Batch start={start} sort={sort}: {e}")
            print(f"[FetchRankings] Unexpected error at start={start}: {e}", flush=True)
            break

    return all_players, errors


# Valid sort_type values for Yahoo Fantasy API
# "prev_season" is a custom value: fetches previous year's full season stats
_VALID_SORT_TYPES = ("season", "date", "lastweek", "lastmonth", "prev_season")


@router.post("/fetch-rankings/{year}")
async def fetch_yahoo_rankings(
    year: int,
    sort_type: str = "season",
    user: dict = Depends(get_current_commissioner),
):
    """Fetch player rankings + stats from Yahoo Fantasy API and store in DB.

    Three-pass fetch:
    1. sort=OR (Overall Rank) — current year rankings + projected stats -> proj_* columns
    2. sort=AR (Actual Rank) — in-season performance ranking
    3. Season stats -> stat_* columns (data source depends on sort_type)

    The sort_type parameter controls what stats are fetched:
    - season (default): current year full season stats
    - lastweek: current year last week stats
    - lastmonth: current year last month stats
    - date: current year today's stats
    - prev_season: previous year full season stats (e.g. 2025 for year=2026)

    Commissioner only. Takes about 40-60 seconds due to API pagination.
    """
    if sort_type not in _VALID_SORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_type '{sort_type}'. Must be one of: {', '.join(_VALID_SORT_TYPES)}",
        )

    league_key = _resolve_league_key(year)
    print(f"[FetchRankings] Starting for year {year}, league_key={league_key}, sort_type={sort_type}", flush=True)

    # === Pass 1: Overall Rank (OR) — current season stats -> proj_* ===
    print("[FetchRankings] Pass 1: Fetching OR (Overall Rank) + current season stats...", flush=True)
    or_players, or_errors = _fetch_yahoo_players_batch(
        league_key, sort="OR", sort_type=sort_type,
        stat_prefix="proj",
    )

    if not or_players:
        raise HTTPException(
            status_code=502,
            detail="No player data returned from Yahoo API (OR pass)",
        )

    # Assign o_rank from the sorted position
    for p in or_players:
        p["o_rank"] = p.pop("_rank", None)

    # Store OR data in database
    bulk_upsert_player_rankings(year, or_players)

    # === Pass 2: Actual Rank (AR) ===
    print("[FetchRankings] Pass 2: Fetching AR (Actual Rank)...", flush=True)
    ar_players, ar_errors = _fetch_yahoo_players_batch(
        league_key, sort="AR", sort_type=sort_type,
    )

    # Build AR rank mapping: player_key -> ar_rank
    ar_rank_map: dict[str, int] = {}
    for p in ar_players:
        ar_rank_map[p["player_key"]] = p.get("_rank", 0)

    # Update AR ranks in database
    if ar_rank_map:
        update_ar_ranks(year, ar_rank_map)

    # === Pass 3: Season Stats -> stat_* columns ===
    # "prev_season" -> fetch previous year's full-season stats (2025)
    # Otherwise -> fetch current year stats with sort_type time range (2026)
    stats_count = 0
    stats_errors: list[str] = []

    if sort_type == "prev_season":
        # Fetch previous year's full-season stats
        stats_year = year - 1
        stats_game_key = _YAHOO_GAME_KEYS.get(stats_year)
        stats_league_num = _YAHOO_LEAGUE_NUMS.get(stats_year)
        stats_sort_type = "season"
        stats_label = f"previous season ({stats_year})"
    else:
        # Fetch current year stats with the selected time range
        stats_year = year
        stats_game_key = _YAHOO_GAME_KEYS.get(stats_year)
        stats_league_num = _YAHOO_LEAGUE_NUMS.get(stats_year)
        stats_sort_type = sort_type
        stats_label = f"current season ({stats_year}, {sort_type})"

    if stats_game_key and stats_league_num:
        stats_league_key = f"{stats_game_key}.l.{stats_league_num}"
        print(
            f"[FetchRankings] Pass 3: Fetching {stats_label} stats "
            f"from league_key={stats_league_key}...",
            flush=True,
        )
        try:
            stats_players, stats_errors = _fetch_yahoo_players_batch(
                stats_league_key, sort="OR", sort_type=stats_sort_type,
                stat_prefix="stat",
            )
            stats_count = len(stats_players)
            if stats_players:
                update_last_season_stats(year, stats_players, sort_type=sort_type)
        except HTTPException:
            stats_errors.append(f"Could not fetch {stats_label} data")
            print(
                f"[FetchRankings] Pass 3: Failed to fetch {stats_label} stats",
                flush=True,
            )
        except Exception as e:
            stats_errors.append(f"Stats fetch error: {e}")
            print(f"[FetchRankings] Pass 3: Unexpected error: {e}", flush=True)
    else:
        reason = "no game key" if not stats_game_key else "no league number"
        print(
            f"[FetchRankings] Pass 3: Skipped — {reason} for year {stats_year}",
            flush=True,
        )

    all_errors = or_errors + ar_errors + stats_errors

    return {
        "message": (
            f"Successfully fetched {len(or_players)} OR rankings "
            f"+ {len(ar_players)} AR rankings "
            f"+ {stats_count} {stats_label} stats for {year}"
        ),
        "year": year,
        "total_fetched": len(or_players),
        "ar_fetched": len(ar_players),
        "stats_fetched": stats_count,
        "sort_type": sort_type,
        "errors": all_errors if all_errors else None,
    }


@router.get("/ranking-status/{year}")
async def get_ranking_status_endpoint(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get the last fetch time and count for player rankings. Commissioner only."""
    status = get_ranking_fetch_status(year)
    return {"year": year, **status}


@router.post("/reload-prospects")
async def reload_prospects(
    user: dict = Depends(get_current_commissioner),
):
    """Reload top 100 prospects data from JSON file. Commissioner only.

    Clears the in-memory cache and re-reads data/top_100_prospects.json.
    """
    from api.routers.players import clear_prospects_cache, _load_prospects_json

    clear_prospects_cache()
    data = _load_prospects_json()
    count = len(data.get("prospects", []))
    return {
        "message": f"Reloaded {count} prospects for {data.get('year', 'unknown')}",
        "count": count,
        "source": data.get("source", ""),
        "updated_at": data.get("updated_at", ""),
    }


@router.post("/sync-rosters/{year}")
async def sync_rosters(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Fetch latest Yahoo rosters and rebuild next-year snapshot. Commissioner only.

    1. Fetch all 16 team rosters from Yahoo API
    2. Save to data/yahoo_{year}_rosters.json
    3. Rebuild year+1 snapshot in DB
    """
    import asyncio
    from src.notification.scheduler import sync_rosters_and_rebuild
    try:
        # Run in thread pool to avoid blocking the event loop
        # (sync_rosters_and_rebuild uses time.sleep for rate limiting)
        result = await asyncio.to_thread(sync_rosters_and_rebuild, year)
        if result is None:
            raise HTTPException(
                status_code=500,
                detail="Sync returned no result. Check server logs for details."
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch-draft-data/{year}")
async def fetch_draft_data(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Fetch draft + transaction + league settings from Yahoo for a year.

    Stores data as JSON files in data/ directory for analytics.
    Commissioner only (requires Yahoo token).
    """
    import json as json_module
    from pathlib import Path
    from api.yahoo_service import (
        discover_league_keys,
        fetch_draft_results,
        fetch_league_settings,
        fetch_transactions_full,
    )

    data_dir = Path(__file__).resolve().parents[2] / "data"

    # Discover league keys
    try:
        keys = discover_league_keys()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Yahoo API error: {e}")

    if year not in keys:
        raise HTTPException(
            status_code=404,
            detail=f"No league found for year {year}. Available: {sorted(keys.keys())}",
        )

    league_key = keys[year]
    results = {"year": year, "league_key": league_key, "files_written": []}

    # Fetch draft results
    try:
        draft = fetch_draft_results(league_key)
        path = data_dir / f"yahoo_{year}_draft.json"
        path.write_text(json_module.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
        results["files_written"].append(str(path.name))
        results["draft_picks"] = len(draft)
    except Exception as e:
        results["draft_error"] = str(e)

    # Fetch league settings
    try:
        settings = fetch_league_settings(league_key)
        path = data_dir / f"yahoo_{year}_league_settings.json"
        path.write_text(json_module.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        results["files_written"].append(str(path.name))
        results["faab_budget"] = settings.get("faab_budget", "unknown")
    except Exception as e:
        results["settings_error"] = str(e)

    # Fetch transactions
    try:
        txs = fetch_transactions_full(league_key)
        path = data_dir / f"yahoo_{year}_transactions.json"
        path.write_text(json_module.dumps(txs, indent=2, ensure_ascii=False), encoding="utf-8")
        results["files_written"].append(str(path.name))
        results["transactions"] = len(txs.get("transactions", []))
    except Exception as e:
        results["transactions_error"] = str(e)

    return results


@router.get("/draft-data/available-years")
async def get_available_draft_years(
    user: dict = Depends(get_current_commissioner),
):
    """List years with available draft data files."""
    from src.analytics.draft_stats import _available_years
    years = _available_years()
    return {"years": years}


@router.post("/rookie-monitor/{year}/check")
async def check_rookie_callups_endpoint(
    year: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_commissioner),
):
    """Manually trigger rookie call-up check. Commissioner only.

    Runs in the background because scanning every R-contract player against
    MLB Stats API can exceed client timeouts. Check Zeabur logs / LINE for
    actual results.
    """
    from src.notification.rookie_monitor import send_callup_notifications

    def _run_bg() -> None:
        try:
            send_callup_notifications(year)
        except Exception as e:
            print(f"[CommissionerAPI] Background rookie monitor failed: {e}")

    background_tasks.add_task(_run_bg)
    return {
        "success": True,
        "status": "scheduled",
        "message": "Rookie call-up check dispatched in background. Check LINE / Zeabur logs in 30-90s.",
    }


@router.get("/rookie-monitor/{year}/log")
async def get_rookie_callup_log(
    year: int,
    user: dict = Depends(get_current_commissioner),
):
    """Get rookie call-up notification log for a season. Commissioner only."""
    from api.database import get_db

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT player_name, player_key, mlb_team,
                          owner_manager, owner_team_id,
                          callup_date, detection_source, notified_at
                   FROM rookie_callup_log
                   WHERE year = %s
                   ORDER BY notified_at DESC""",
                (year,),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"year": year, "callups": rows, "count": len(rows)}
    finally:
        conn.close()
