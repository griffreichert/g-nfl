"""Per-picker PIN, exchanged for a signed token (#60).

Until now `POST /api/picks` took the picker from the request body, so anyone
could submit as anyone. The pool is six family members and two models, and the
whole point of the ledger is that a week's picks are attributable, so the entry
that loses an argument on the call cannot be quietly rewritten afterwards.

Threat model is a cousin, not an attacker. A four-digit PIN over HTTPS is
proportionate. What is not proportionate is storing those PINs in the clear, so
the environment holds PBKDF2 hashes and `scripts/make_pin.py` generates them.

Configuration, both on Render and in `.env`:

    AUTH_SECRET   long random string; signs the tokens
    PICKER_PINS   {"Griffin": "<hash from make_pin.py>", ...}

With `PICKER_PINS` unset every login fails, which is the right default for a
deploy nobody has configured yet.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

#: PBKDF2-HMAC-SHA256. 600k iterations is the OWASP 2023 figure for this
#: primitive, and a four-digit PIN needs the work factor more than a password
#: does: the whole keyspace is 10,000 guesses.
ITERATIONS = 600_000
ALGORITHM = "HS256"

#: Long enough that the room is not logging in every Sunday, short enough that
#: a lost phone stops mattering before the season ends.
TOKEN_DAYS = 30

bearer = HTTPBearer(auto_error=False)

# FastAPI reads dependencies out of argument defaults, which is exactly what
# ruff's B008 warns about. The call is the framework's API, so it is bound once
# here rather than repeated at every call site.
_BEARER = Depends(bearer)


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    """`salt$hash`, both hex. What `PICKER_PINS` stores."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Constant-time check of a PIN against a `salt$hash` string."""
    try:
        salt_hex, digest_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ITERATIONS)
    return hmac.compare_digest(candidate.hex(), digest_hex)


def _pins() -> dict[str, str]:
    raw = os.getenv("PICKER_PINS", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # a malformed env var must fail every login, never allow all of them
        return {}


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


def authenticate(picker: str, pin: str) -> str:
    """Check a PIN and mint a token, or raise 401.

    The same message covers an unknown picker and a wrong PIN, so the response
    does not confirm who is in the pool.
    """
    stored = _pins().get(picker)
    if not stored or not verify_pin(pin, stored):
        raise HTTPException(401, "Wrong picker or PIN")

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
    body, which is what closes the impersonation hole.
    """
    if creds is None:
        raise HTTPException(401, "Sign in to do that")
    return read_token(creds.credentials)
