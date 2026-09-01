"""One passphrase for the room, then you say who you are (#60).

The site is six family members and two models. Everyone in it is trusted, so
the passphrase exists to keep the internet out and nothing more. Once you are
in, you choose your name from a dropdown and the API takes your word for it.

The token still carries the name, so every endpoint that writes reads the
picker from `require_picker` and ignores whatever the request body claims.
That keeps one browser session pinned to one name, which is what stops a stale
tab saving Harry's week under Chuck.

Configuration, both on Render and in `.env`:

    AUTH_SECRET      long random string; signs the tokens
    APP_PASSPHRASE   the one passphrase the room shares

With `APP_PASSPHRASE` unset every login fails, which is the right default for a
deploy nobody has configured yet.

Per-picker PINs did this job until 2026-09-01. That code is kept and tested in
`pins.py`, unwired, with the two-line change that turns it back on.
"""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGORITHM = "HS256"

#: Long enough that the room is not logging in every Sunday, short enough that
#: a lost phone stops mattering before the season ends.
TOKEN_DAYS = 30

bearer = HTTPBearer(auto_error=False)

# FastAPI reads dependencies out of argument defaults, which is exactly what
# ruff's B008 warns about. The call is the framework's API, so it is bound once
# here rather than repeated at every call site.
_BEARER = Depends(bearer)


def _passphrase() -> str:
    """The configured passphrase, or empty when nobody has set one."""
    return os.getenv("APP_PASSPHRASE", "").strip()


#: RFC 7518 3.2 for HS256. PyJWT warns below this; refusing is better than
#: warning, because a short secret is guessable and nobody reads deploy logs.
MIN_SECRET_BYTES = 32


def _secret() -> str:
    secret = os.getenv("AUTH_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "AUTH_SECRET is not configured")
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise HTTPException(
            503, f"AUTH_SECRET must be at least {MIN_SECRET_BYTES} bytes"
        )
    return secret


def check_passphrase(passphrase: str) -> bool:
    """Constant-time check against `APP_PASSPHRASE`.

    An unset passphrase fails every attempt rather than allowing all of them.
    """
    expected = _passphrase()
    if not expected:
        return False
    return hmac.compare_digest(passphrase.strip(), expected)


def authenticate(picker: str, passphrase: str) -> str:
    """Check the passphrase and mint a token naming `picker`, or raise 401."""
    if not check_passphrase(passphrase):
        raise HTTPException(401, "Wrong passphrase")

    expires = datetime.now(UTC) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": picker, "exp": expires}, _secret(), algorithm=ALGORITHM)


def read_token(token: str) -> str:
    """The picker a token belongs to, or 401."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, sign in again") from None
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session") from None
    picker = claims.get("sub")
    if not picker:
        raise HTTPException(401, "Invalid session")
    return picker


def require_picker(
    creds: HTTPAuthorizationCredentials | None = _BEARER,
) -> str:
    """FastAPI dependency: the signed-in picker.

    Endpoints that write take the picker from here and ignore anything in the
    body, so a session stays pinned to the name it signed in with.
    """
    if creds is None:
        raise HTTPException(401, "Sign in to do that")
    return read_token(creds.credentials)
