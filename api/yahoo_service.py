"""
Yahoo Fantasy API service - DB-backed token management.

For use by backend services and background jobs that need Yahoo API access
without relying on filesystem (oauth2.json).

Falls back to oauth2.json if no DB tokens exist (local dev compatibility).
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

# Buffer before expiry to trigger proactive refresh (5 minutes)
_REFRESH_BUFFER_SECONDS = 300


class YahooTokenError(Exception):
    """Raised when Yahoo token is missing or refresh fails."""
    pass


def _get_client_credentials() -> tuple[str, str]:
    """Get Yahoo OAuth client ID and secret from env vars."""
    client_id = os.getenv("YAHOO_CLIENT_ID", "")
    client_secret = os.getenv("YAHOO_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise YahooTokenError(
            "YAHOO_CLIENT_ID / YAHOO_CLIENT_SECRET env vars not set"
        )
    return client_id, client_secret


def _try_oauth2_json_fallback() -> Optional[str]:
    """Try to load access token from oauth2.json (local dev fallback)."""
    oauth_file = Path(__file__).resolve().parent.parent / "oauth2.json"
    if not oauth_file.exists():
        return None
    try:
        creds = json.loads(oauth_file.read_text())
        token = creds.get("access_token", "")
        if token:
            print("[YahooService] Using oauth2.json fallback (local dev)", flush=True)
            return token
    except Exception:
        pass
    return None


def get_valid_access_token() -> str:
    """
    Get a valid Yahoo access token.

    Priority:
    1. DB-backed commissioner token (auto-refresh if expired)
    2. oauth2.json fallback (local dev)

    Returns: valid access_token string
    Raises: YahooTokenError if no token available
    """
    from api.database import get_commissioner_yahoo_token

    token_row = get_commissioner_yahoo_token()

    if token_row:
        # Check if token is still valid (with buffer)
        expires_at = token_row.get("expires_at")
        now = datetime.datetime.now(datetime.timezone.utc)

        if expires_at:
            # Handle timezone-naive datetimes from DB
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            if now >= expires_at - datetime.timedelta(seconds=_REFRESH_BUFFER_SECONDS):
                # Token expired or about to expire, refresh it
                return refresh_db_token(token_row)

        return token_row["access_token"]

    # Fallback to oauth2.json for local dev
    fallback_token = _try_oauth2_json_fallback()
    if fallback_token:
        return fallback_token

    raise YahooTokenError(
        "No Yahoo token available. Commissioner must log in via Yahoo OAuth."
    )


def refresh_db_token(token_row: dict) -> str:
    """
    Refresh an expired token using the refresh_token from DB.
    Updates DB with new access_token and rotated refresh_token.

    Returns: new access_token
    Raises: YahooTokenError if refresh fails
    """
    from api.database import upsert_yahoo_token

    refresh_token = token_row.get("refresh_token", "")
    if not refresh_token:
        raise YahooTokenError("No refresh_token available. Commissioner must re-login.")

    client_id, client_secret = _get_client_credentials()

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=HTTPBasicAuth(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise YahooTokenError(f"Token refresh request failed: {e}")

    if resp.status_code != 200:
        raise YahooTokenError(
            f"Token refresh failed ({resp.status_code}): {resp.text[:300]}"
        )

    data = resp.json()
    new_access_token = data["access_token"]
    new_refresh_token = data.get("refresh_token", refresh_token)
    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=expires_in
    )

    # Update DB
    upsert_yahoo_token(
        user_id=token_row["user_id"],
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=expires_at,
        yahoo_guid=token_row.get("yahoo_guid", ""),
    )

    print(
        f"[YahooService] Token refreshed for user #{token_row['user_id']}, "
        f"expires at {expires_at.isoformat()}",
        flush=True,
    )
    return new_access_token


def yahoo_api_get(path: str) -> dict:
    """
    Perform a GET request to Yahoo Fantasy API with auto-refresh.
    Retries once on 401.

    Args:
        path: API path (e.g., "/league/469.l.80910/standings")

    Returns:
        Parsed JSON response

    Raises:
        YahooTokenError: if no valid token
        RuntimeError: if API call fails after retry
    """
    url = f"{BASE_URL}{path}"
    separator = "&" if "?" in url else "?"
    url += f"{separator}format=json"

    access_token = get_valid_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers, timeout=15)

    # Retry once on 401 (token may have expired between check and request)
    if resp.status_code == 401:
        print("[YahooService] Got 401, forcing token refresh and retry", flush=True)
        from api.database import get_commissioner_yahoo_token
        token_row = get_commissioner_yahoo_token()
        if token_row:
            access_token = refresh_db_token(token_row)
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Yahoo API request failed ({resp.status_code}): {resp.text[:300]}"
        )

    return resp.json()


def get_token_status() -> dict:
    """
    Get current Yahoo token connection status for dashboard display.

    Returns dict with: connected, user_id, yahoo_guid, expires_at,
                       is_expired, updated_at, message
    """
    from api.database import get_commissioner_yahoo_token

    token_row = get_commissioner_yahoo_token()

    if not token_row:
        return {
            "connected": False,
            "user_id": None,
            "yahoo_guid": "",
            "expires_at": None,
            "is_expired": False,
            "updated_at": None,
            "message": "Yahoo API 尚未連結 Not connected",
        }

    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = token_row.get("expires_at")
    is_expired = False

    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        is_expired = now >= expires_at

    updated_at = token_row.get("updated_at")

    return {
        "connected": True,
        "user_id": token_row.get("user_id"),
        "yahoo_guid": token_row.get("yahoo_guid", ""),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "is_expired": is_expired,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "message": (
            "Token 已過期，請重新整理或重新登入 Token expired"
            if is_expired
            else "Yahoo API 已連結 Connected"
        ),
    }
