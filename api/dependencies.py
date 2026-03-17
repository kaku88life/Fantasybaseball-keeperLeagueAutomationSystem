"""
Fantasy Baseball Keeper League - FastAPI Dependencies

JWT authentication and database dependency injection.
Supports both HttpOnly cookie and Authorization header for JWT tokens.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, Response, status
from jose import JWTError, jwt

from api.database import get_user_by_id

# Support both JWT_SECRET and JWT_SECRET_KEY env var names
_jwt_secret = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY", "")
if not _jwt_secret:
    # Local development: allow a default secret
    _jwt_secret = "dev-secret-local-only"
    print("[WARNING] JWT_SECRET / JWT_SECRET_KEY not set. Using dev default. "
          "Set the env var before deploying to production!")
elif _jwt_secret == "dev-secret-change-in-production":
    print("[WARNING] JWT secret is still the placeholder value. "
          "Please set a strong JWT_SECRET_KEY for production!")
JWT_SECRET = _jwt_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

# Cookie configuration
AUTH_COOKIE_NAME = "auth_token"
_is_production = bool(os.getenv("FRONTEND_URL", "").startswith("https"))


def create_jwt_token(user_id: int, is_commissioner: bool = False) -> str:
    """Create a JWT token for a user."""
    import datetime
    payload = {
        "sub": str(user_id),
        "is_commissioner": is_commissioner,
        "exp": datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def set_auth_cookie(response: Response, token: str) -> None:
    """Set HttpOnly auth cookie on a response."""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,              # Works on localhost in modern browsers
        samesite="none",          # Required for cross-origin (frontend != backend)
        max_age=JWT_EXPIRE_DAYS * 86400,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear auth cookie from a response."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def _extract_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    """Extract JWT token from cookie (priority) or Authorization header (fallback)."""
    # 1. Try HttpOnly cookie first
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    # 2. Fallback to Authorization header (backward compatibility)
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]

    return None


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Dependency: extract current user from HttpOnly cookie or Authorization header."""
    token = _extract_token(request, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    payload = decode_jwt_token(token)

    user_id = int(payload["sub"])
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def get_current_commissioner(
    user: dict = Depends(get_current_user),
) -> dict:
    """Dependency: require commissioner role."""
    if not user.get("is_commissioner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Commissioner access required",
        )
    return user


async def get_optional_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    """Dependency: optionally extract current user (returns None if no auth)."""
    token = _extract_token(request, authorization)
    if not token:
        return None
    try:
        payload = decode_jwt_token(token)
        user_id = int(payload["sub"])
        return get_user_by_id(user_id)
    except (HTTPException, ValueError):
        return None
