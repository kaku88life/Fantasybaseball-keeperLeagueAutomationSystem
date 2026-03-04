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
from api.schemas import CallbackResponse, UserInfoSchema

router = APIRouter()

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_PROFILE_URL = "https://api.login.yahoo.com/openid/v1/userinfo"

# State tokens for CSRF protection (in-memory, simple for 16-user app)
_pending_states: set[str] = set()


def _fullwidth_to_halfwidth(text: str) -> str:
    """Convert fullwidth ASCII characters to halfwidth (e.g. 'Ｋａｋｕ' -> 'Kaku')."""
    result = []
    for ch in text:
        code = ord(ch)
        # Fullwidth ASCII: U+FF01 (!) to U+FF5E (~) -> halfwidth U+0021 to U+007E
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        # Fullwidth space U+3000 -> halfwidth space
        elif code == 0x3000:
            result.append(" ")
        else:
            result.append(ch)
    return "".join(result)


def _extract_from_nested(data, key: str) -> str:
    """Recursively search for a key in deeply nested Yahoo API JSON."""
    if isinstance(data, dict):
        if key in data and isinstance(data[key], str):
            return data[key]
        for v in data.values():
            result = _extract_from_nested(v, key)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_from_nested(item, key)
            if result:
                return result
    return ""


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


@router.get("/yahoo/login")
async def yahoo_login():
    """Start Yahoo OAuth2 authorization flow.
    Redirects the browser directly to Yahoo for authentication.
    """
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
    return RedirectResponse(auth_url)


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
    code: str = Query(None),
    state: str = Query(""),
    error: str = Query(None),
    error_description: str = Query(""),
):
    """
    Yahoo OAuth callback. Yahoo redirects here after user authorization.
    On success: ?code=xxx&state=yyy
    On failure: ?error=xxx&error_description=yyy
    """
    from urllib.parse import quote
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")

    # Handle Yahoo error response (user denied access, etc.)
    if error:
        msg = error_description or error
        print(f"[AUTH DEBUG] Yahoo returned error: {error} - {error_description}", flush=True)
        return RedirectResponse(
            f"{frontend_url}/auth/callback?error={quote(msg)}"
        )

    if not code:
        return RedirectResponse(
            f"{frontend_url}/auth/callback?error={quote('No authorization code received from Yahoo')}"
        )

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
            f"{frontend_url}/auth/callback?error={quote(str(e.detail))}"
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

    print(f"[AUTH DEBUG] Token response keys: {list(token_data.keys())}", flush=True)
    print(f"[AUTH DEBUG] xoauth_yahoo_guid from token: '{yahoo_guid}'", flush=True)

    # Decode id_token JWT to extract sub (GUID), nickname, email
    nickname = ""
    email = ""
    id_payload = {}
    if "id_token" in token_data:
        try:
            import base64
            import json
            payload_b64 = token_data["id_token"].split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            id_payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            print(f"[AUTH DEBUG] id_token claims: {list(id_payload.keys())}", flush=True)
            if not yahoo_guid:
                yahoo_guid = id_payload.get("sub", "")
            nickname = id_payload.get("nickname", id_payload.get("preferred_username", id_payload.get("name", "")))
            email = id_payload.get("email", "")
            print(f"[AUTH DEBUG] From id_token - GUID: '{yahoo_guid}', nickname: '{nickname}', email: '{email}'", flush=True)
        except Exception as e:
            print(f"[AUTH DEBUG] Failed to decode id_token: {e}", flush=True)

    # Fallback: fetch user profile from userinfo endpoint
    if not yahoo_guid or not nickname:
        profile_resp = requests.get(
            YAHOO_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if profile_resp.status_code == 200:
            profile = profile_resp.json()
            if not yahoo_guid:
                yahoo_guid = profile.get("sub", profile.get("guid", profile.get("user_id", "")))
            if not nickname:
                nickname = profile.get("nickname", profile.get("preferred_username", profile.get("name", "")))
            if not email:
                email = profile.get("email", "")
            print(f"[AUTH DEBUG] From profile: GUID='{yahoo_guid}', nickname='{nickname}'", flush=True)
        else:
            print(f"[AUTH DEBUG] Profile fetch failed: {profile_resp.status_code} (using id_token data only)", flush=True)

    if not yahoo_guid:
        raise HTTPException(status_code=400, detail="Could not determine Yahoo user ID")

    # If no nickname yet, try Yahoo Fantasy API endpoints
    if not nickname:
        # Try multiple Fantasy API endpoints to find display name
        fantasy_urls = [
            "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/profile?format=json",
            "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_codes=mlb/teams?format=json",
        ]
        for url in fantasy_urls:
            if nickname:
                break
            try:
                fantasy_resp = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                print(f"[AUTH DEBUG] Fantasy API {url.split('/')[-1]}: status={fantasy_resp.status_code}", flush=True)
                if fantasy_resp.status_code == 200:
                    fu_data = fantasy_resp.json()
                    fu_str = str(fu_data)
                    print(f"[AUTH DEBUG] Fantasy response: {fu_str[:500]}", flush=True)
                    # Search for display_name or nickname in the response
                    nickname = _extract_from_nested(fu_data, "display_name")
                    if not nickname:
                        nickname = _extract_from_nested(fu_data, "nickname")
                    # Convert fullwidth chars to halfwidth (Yahoo sometimes uses fullwidth)
                    if nickname:
                        nickname = _fullwidth_to_halfwidth(nickname)
                    print(f"[AUTH DEBUG] Extracted nickname: '{nickname}'", flush=True)
            except Exception as e:
                print(f"[AUTH DEBUG] Fantasy API error: {e}", flush=True)

    # Try to match user to a team via Yahoo Fantasy API
    team_id, fantasy_nickname = _match_user_to_team(access_token, yahoo_guid, nickname)
    if not nickname and fantasy_nickname:
        nickname = fantasy_nickname
        print(f"[AUTH DEBUG] Got nickname from team matching: '{nickname}'", flush=True)

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


def _match_user_to_team(access_token: str, yahoo_guid: str, nickname: str) -> tuple[int | None, str]:
    """
    Try to match a Yahoo user to a team in the database.
    Returns (team_id, nickname_from_fantasy_api).

    Strategy:
    1. Check if user already has a team_id in the database
    2. Try Yahoo Fantasy API to find their team via manager GUID
    3. Fallback: match by nickname against MANAGER_NAME_MAPPING
    """
    fantasy_nickname = ""

    # 1. Check existing mapping
    existing = get_user_by_guid(yahoo_guid)
    if existing and existing.get("team_id"):
        return existing["team_id"], fantasy_nickname

    # 2. Try Yahoo Fantasy API to find their team
    try:
        team_id, fantasy_nickname = _match_via_yahoo_api(access_token, yahoo_guid)
        if team_id:
            return team_id, fantasy_nickname
    except Exception as e:
        print(f"[AUTH DEBUG] _match_via_yahoo_api error: {e}", flush=True)

    # 3. Fallback: match by nickname
    try:
        team_id = _match_by_nickname(nickname)
        if team_id:
            return team_id, fantasy_nickname
    except Exception as e:
        print(f"[AUTH DEBUG] _match_by_nickname error: {e}", flush=True)

    return None, fantasy_nickname


def _match_via_yahoo_api(access_token: str, yahoo_guid: str) -> tuple[int | None, str]:
    """Use Yahoo Fantasy API to find which team this user manages.
    Returns (team_id, manager_nickname).
    """
    found_nickname = ""

    # Get user's leagues
    resp = requests.get(
        "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_codes=mlb/leagues?format=json",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[AUTH DEBUG] Fantasy leagues API failed: {resp.status_code}", flush=True)
        return None, found_nickname

    data = resp.json()
    # Find our keeper league
    league_id = os.getenv("YAHOO_LEAGUE_ID", "")
    if not league_id:
        return None, found_nickname

    # Find the league key that ends with our league number
    league_num = league_id.split(".")[-1] if "." in league_id else league_id

    from api.database import get_all_teams as _get_teams
    db_teams = _get_teams()
    if not db_teams:
        return None, found_nickname

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
                                        found_nickname = mgr.get("nickname", "")
                                        print(f"[AUTH DEBUG] Found manager in Fantasy API: nickname='{found_nickname}'", flush=True)
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
                                                    return dbt["id"], found_nickname
                                        # Try matching by manager nickname
                                        if found_nickname:
                                            tid = _match_by_nickname(found_nickname)
                                            if tid:
                                                return tid, found_nickname
                                        return None, found_nickname
        break  # Only try the most recent game key that works

    return None, found_nickname


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
