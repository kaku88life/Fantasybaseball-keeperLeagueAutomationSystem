"""
Fantasy Baseball Keeper League - Yahoo OAuth Authentication Routes
"""
from __future__ import annotations

import os
import secrets
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from api.database import (
    get_all_teams,
    get_team_by_id,
    get_user_by_guid,
    upsert_user,
)
from api.dependencies import create_jwt_token, get_current_user
from api.schemas import CallbackResponse, LoginResponse, UserInfoSchema

router = APIRouter()

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_PROFILE_URL = "https://api.login.yahoo.com/openid/v1/userinfo"

# State tokens for CSRF protection (in-memory, simple for 16-user app)
_pending_states: set[str] = set()


def _get_yahoo_client_id() -> str:
    cid = os.getenv("YAHOO_CLIENT_ID")
    if not cid:
        raise HTTPException(status_code=500, detail="YAHOO_CLIENT_ID not configured")
    return cid


def _get_yahoo_client_secret() -> str:
    secret = os.getenv("YAHOO_CLIENT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="YAHOO_CLIENT_SECRET not configured")
    return secret


def _get_redirect_uri() -> str:
    """Return the OAuth redirect URI.
    Uses 'oob' (out-of-band) for local dev to avoid Yahoo's https requirement.
    For production, set OAUTH_REDIRECT_URI env var to the https backend callback URL.
    """
    return os.getenv("OAUTH_REDIRECT_URI", "oob")


@router.post("/yahoo/login", response_model=LoginResponse)
async def yahoo_login():
    """Start Yahoo OAuth2 authorization flow. Returns the Yahoo auth URL."""
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    params = {
        "client_id": _get_yahoo_client_id(),
        "redirect_uri": _get_redirect_uri(),
        "response_type": "code",
        "scope": "openid",
        "state": state,
    }
    auth_url = f"{YAHOO_AUTH_URL}?{urlencode(params)}"
    return LoginResponse(auth_url=auth_url)


@router.post("/yahoo/exchange")
async def yahoo_exchange_code(
    code: str = Query(...),
) -> CallbackResponse:
    """
    Exchange a Yahoo authorization code for a JWT token.
    Used with OOB flow: user copies the code from Yahoo and pastes it in the frontend.
    Also used as the general code-exchange endpoint for production redirect flow.
    """
    return await _exchange_code_for_jwt(code)


@router.get("/yahoo/callback")
async def yahoo_callback(
    code: str = Query(...),
    state: str = Query(""),
):
    """
    Yahoo OAuth callback (production only, when OAUTH_REDIRECT_URI is set to a https URL).
    Yahoo redirects here with the auth code, backend processes it and
    redirects to frontend /auth/callback?token=xxx.
    """
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")

    # Validate state
    if state and state not in _pending_states:
        return RedirectResponse(
            f"{frontend_url}/auth/callback?error=invalid_state"
        )
    _pending_states.discard(state)

    try:
        result = await _exchange_code_for_jwt(code)
        return RedirectResponse(
            f"{frontend_url}/auth/callback?token={result.token}"
        )
    except HTTPException as e:
        return RedirectResponse(
            f"{frontend_url}/auth/callback?error={e.detail}"
        )


async def _exchange_code_for_jwt(code: str) -> CallbackResponse:
    """Core logic: exchange Yahoo auth code for JWT token."""
    # Exchange code for access token
    token_resp = requests.post(
        YAHOO_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _get_redirect_uri(),
            "client_id": _get_yahoo_client_id(),
            "client_secret": _get_yahoo_client_secret(),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )

    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to exchange code: {token_resp.text}",
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    yahoo_guid = token_data.get("xoauth_yahoo_guid", "")

    # Fetch user profile
    profile_resp = requests.get(
        YAHOO_PROFILE_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )

    nickname = ""
    email = ""
    if profile_resp.status_code == 200:
        profile = profile_resp.json()
        nickname = profile.get("nickname", profile.get("name", ""))
        email = profile.get("email", "")

    if not yahoo_guid:
        yahoo_guid = profile.get("sub", "") if profile_resp.status_code == 200 else ""

    if not yahoo_guid:
        raise HTTPException(status_code=400, detail="Could not determine Yahoo user ID")

    # Try to match user to a team via Yahoo Fantasy API
    team_id = _match_user_to_team(access_token, yahoo_guid, nickname)

    # Check if this user should be commissioner
    existing = get_user_by_guid(yahoo_guid)
    is_commissioner = bool(existing and existing.get("is_commissioner"))

    # Upsert user
    user = upsert_user(
        yahoo_guid=yahoo_guid,
        yahoo_nickname=nickname,
        yahoo_email=email,
        team_id=team_id,
        is_commissioner=is_commissioner,
    )

    # Create JWT
    jwt_token = create_jwt_token(user["id"], is_commissioner=is_commissioner)

    # Build response
    team = get_team_by_id(user["team_id"]) if user.get("team_id") else None
    user_info = UserInfoSchema(
        user_id=user["id"],
        yahoo_guid=yahoo_guid,
        yahoo_nickname=nickname,
        team_id=user.get("team_id"),
        team_name=team["team_name"] if team else None,
        manager_name=team["manager_name"] if team else None,
        is_commissioner=is_commissioner,
    )

    return CallbackResponse(token=jwt_token, user=user_info)


def _match_user_to_team(access_token: str, yahoo_guid: str, nickname: str) -> int | None:
    """
    Try to match a Yahoo user to a team in the database.

    Strategy:
    1. Check if user already has a team_id in the database
    2. Try Yahoo Fantasy API to find their team via manager GUID
    3. Fallback: match by nickname against MANAGER_NAME_MAPPING
    """
    # 1. Check existing mapping
    existing = get_user_by_guid(yahoo_guid)
    if existing and existing.get("team_id"):
        return existing["team_id"]

    # 2. Try Yahoo Fantasy API to find their team
    try:
        team_id = _match_via_yahoo_api(access_token, yahoo_guid)
        if team_id:
            return team_id
    except Exception:
        pass

    # 3. Fallback: match by nickname
    try:
        team_id = _match_by_nickname(nickname)
        if team_id:
            return team_id
    except Exception:
        pass

    return None


def _match_via_yahoo_api(access_token: str, yahoo_guid: str) -> int | None:
    """Use Yahoo Fantasy API to find which team this user manages."""
    # Get user's leagues
    resp = requests.get(
        "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_codes=mlb/leagues?format=json",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    # Find our keeper league
    league_id = os.getenv("YAHOO_LEAGUE_ID", "")
    if not league_id:
        return None

    # Find the league key that ends with our league number
    league_num = league_id.split(".")[-1] if "." in league_id else league_id

    # Navigate Yahoo's nested JSON to find league keys
    games = (
        data.get("fantasy_content", {})
        .get("users", {})
        .get("0", {})
        .get("user", [{}])
    )
    # This structure is complex and varies; try to extract team info
    # For now, use the simpler approach of fetching teams from our known league
    from api.database import get_all_teams as _get_teams
    db_teams = _get_teams()
    if not db_teams:
        return None

    # Get teams from our league using the user's token
    for game_key in ["469", "458", "431", "422"]:  # recent game keys
        league_key = f"{game_key}.l.{league_num}"
        teams_resp = requests.get(
            f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/teams?format=json",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if teams_resp.status_code != 200:
            continue

        teams_data = teams_resp.json()
        teams_list = (
            teams_data.get("fantasy_content", {})
            .get("league", [{}])
        )
        if len(teams_list) < 2:
            continue

        teams_obj = teams_list[1].get("teams", {})
        count = teams_obj.get("count", 0)

        for i in range(count):
            team_info = teams_obj.get(str(i), {}).get("team", [])
            if not team_info:
                continue
            # Extract manager info
            for item in team_info:
                if isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict) and "managers" in sub:
                            managers = sub["managers"]
                            for mk, mv in managers.items():
                                if isinstance(mv, dict):
                                    mgr = mv.get("manager", {})
                                    if mgr.get("guid") == yahoo_guid:
                                        # Found the team! Match to DB team
                                        team_key = ""
                                        for sub2 in team_info:
                                            if isinstance(sub2, list):
                                                for sub3 in sub2:
                                                    if isinstance(sub3, dict) and "team_key" in sub3:
                                                        team_key = sub3["team_key"]
                                        if team_key:
                                            for dbt in db_teams:
                                                if dbt.get("yahoo_team_id") == team_key:
                                                    return dbt["id"]
                                        # Try matching by manager nickname
                                        mgr_nickname = mgr.get("nickname", "")
                                        if mgr_nickname:
                                            tid = _match_by_nickname(mgr_nickname)
                                            if tid:
                                                return tid
        break  # Only try the most recent game key that works

    return None


def _match_by_nickname(nickname: str) -> int | None:
    """Match a Yahoo nickname to a team via MANAGER_NAME_MAPPING."""
    from config.settings import MANAGER_NAME_MAPPING
    from src.parser.normalizer import normalize_player_name_for_matching

    norm_nick = normalize_player_name_for_matching(nickname)
    if not norm_nick:
        return None

    db_teams = get_all_teams()

    # Check if nickname matches any mapping value
    for excel_name, yahoo_nick in MANAGER_NAME_MAPPING.items():
        norm_yahoo = normalize_player_name_for_matching(yahoo_nick)
        if norm_nick == norm_yahoo or norm_nick in norm_yahoo or norm_yahoo in norm_nick:
            for dbt in db_teams:
                norm_mgr = normalize_player_name_for_matching(dbt["manager_name"])
                norm_excel = normalize_player_name_for_matching(excel_name)
                if norm_mgr == norm_excel or norm_mgr in norm_excel or norm_excel in norm_mgr:
                    return dbt["id"]

    # Direct manager name match
    for dbt in db_teams:
        norm_mgr = normalize_player_name_for_matching(dbt["manager_name"])
        if norm_nick == norm_mgr or norm_nick in norm_mgr or norm_mgr in norm_nick:
            return dbt["id"]

    return None


@router.get("/me", response_model=UserInfoSchema)
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    team = get_team_by_id(user["team_id"]) if user.get("team_id") else None
    return UserInfoSchema(
        user_id=user["id"],
        yahoo_guid=user["yahoo_guid"],
        yahoo_nickname=user.get("yahoo_nickname", ""),
        team_id=user.get("team_id"),
        team_name=team["team_name"] if team else None,
        manager_name=team["manager_name"] if team else None,
        is_commissioner=bool(user.get("is_commissioner")),
    )


@router.post("/logout")
async def logout():
    """Logout (client-side token removal, no server state to clear)."""
    return {"message": "Logged out"}
