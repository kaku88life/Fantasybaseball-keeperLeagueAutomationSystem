"""
Fantasy Baseball Keeper League - Commissioner Admin Routes
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.database import (
    approve_submission,
    delete_submission,
    get_all_submissions,
    get_all_teams,
    get_team_by_id,
    get_user_by_id,
    save_snapshot,
    update_team_adjustments,
    upsert_team,
)
from api.dependencies import get_current_commissioner
from api.schemas import (
    ApproveRequest,
    AssignTeamRequest,
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
    all_teams = get_all_teams()
    submissions = get_all_submissions(year)
    sub_map = {s["team_id"]: s for s in submissions}

    result = []
    for t in all_teams:
        sub = sub_map.get(t["id"])
        result.append(SubmissionStatusSchema(
            team_id=t["id"],
            manager_name=t["manager_name"],
            team_name=t.get("team_name", ""),
            is_submitted=sub is not None,
            submitted_at=sub["submitted_at"] if sub else None,
            is_valid=bool(sub["is_valid"]) if sub else False,
            commissioner_approved=bool(sub["commissioner_approved"]) if sub else False,
            commissioner_notes=sub.get("commissioner_notes", "") if sub else "",
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
    """Approve or reject a team's keeper submission."""
    from api.database import get_submission
    sub = get_submission(year, team_id)
    if not sub:
        raise HTTPException(status_code=404, detail="No submission found")

    approve_submission(year, team_id, body.approved, body.notes)
    action = "approved" if body.approved else "rejected"
    return {"message": f"Submission {action}", "year": year, "team_id": team_id}


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
        conn.execute(
            "UPDATE users SET team_id = ? WHERE id = ?",
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
    from api.database import get_db

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT u.id, u.yahoo_guid, u.yahoo_nickname, u.yahoo_email,
                      u.team_id, u.is_commissioner, u.last_login,
                      t.manager_name, t.team_name
               FROM users u
               LEFT JOIN teams t ON u.team_id = t.id
               ORDER BY u.yahoo_nickname""",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


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
        conn.execute(
            "UPDATE users SET is_commissioner = 1 WHERE id = ?", (user_id,)
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
