"""
Fantasy Baseball Keeper League - FastAPI Dependencies

JWT authentication and database dependency injection.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from api.database import get_user_by_id

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


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


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency: extract current user from JWT token in Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = authorization.split(" ", 1)[1]
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


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Dependency: optionally extract current user (returns None if no auth)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization.split(" ", 1)[1]
        payload = decode_jwt_token(token)
        user_id = int(payload["sub"])
        return get_user_by_id(user_id)
    except (HTTPException, ValueError):
        return None
