"""JWT creation, verification, and the require_auth FastAPI dependency.

Supports two auth transports:
- httpOnly cookie `auth_token` (browser clients via Next.js rewrites)
- Bearer token in Authorization header (API clients / curl)
Bearer takes precedence when both are present.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jose import JWTError, jwt

_bearer = HTTPBearer(auto_error=False)

_ALGORITHM = "HS256"
_SHORT_EXPIRY_HOURS = 8
_LONG_EXPIRY_DAYS = 7


def _secret() -> str:
    return os.environ.get("AUTH_SECRET", "CHANGE_ME_IN_PRODUCTION")


def create_token(email: str, role: str, remember: bool = False) -> str:
    """Return a signed JWT. remember=True gives a 7-day token; default is 8h."""
    delta = timedelta(days=_LONG_EXPIRY_DAYS) if remember else timedelta(hours=_SHORT_EXPIRY_HOURS)
    payload = {
        "sub": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + delta,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency. Returns {"email": ..., "role": ...} or raises 401.

    Checks Bearer token first (API clients), then falls back to the
    httpOnly cookie set by the Next.js login route (browser clients).
    The middleware only checks cookie *existence* for routing — actual
    signature verification always happens here.
    """
    token: str | None = None
    if creds is not None:
        token = creds.credentials
    else:
        token = request.cookies.get("auth_token")

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode(token)
    return {"email": payload["sub"], "role": payload["role"]}
