"""Per-picker PINs. Kept, not wired up (#60).

This was how the site signed people in until 2026-09-01. Each picker had a
four-digit PIN, `PICKER_PINS` held the PBKDF2 hashes, and the name on a session
was proved rather than asserted.

It was swapped for one shared passphrase (`auth.py`) because eight hashes in
one environment variable made changing a single PIN an env edit and a redeploy,
and what the PINs bought was protection against impersonation inside a family
pool. Everyone in the pool is trusted, so the trade was wrong.

The code is here because that reasoning can change: a wider room, a public URL,
or a season where somebody edits a pick after the call.

**To turn it back on**, `authenticate` in `auth.py` becomes:

    def authenticate(picker: str, passphrase: str) -> str:
        if not check_pin(picker, passphrase):
            raise HTTPException(401, "Wrong picker or PIN")
        ...mint the token exactly as now...

Then set `PICKER_PINS` from `scripts/make_pin.py` and relabel the passphrase
field in `web/src/components/SignIn.tsx`. The token already carries the picker,
so nothing downstream of sign-in changes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os

#: PBKDF2-HMAC-SHA256. 600k iterations is the OWASP 2023 figure for this
#: primitive, and a four-digit PIN needs the work factor more than a password
#: does: the whole keyspace is 10,000 guesses.
ITERATIONS = 600_000


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


def load_pins() -> dict[str, str]:
    """`PICKER_PINS` as a dict, empty when unset or malformed."""
    raw = os.getenv("PICKER_PINS", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # a malformed env var must fail every login, never allow all of them
        return {}


def check_pin(picker: str, pin: str) -> bool:
    """Whether this picker's PIN is right. False for an unknown picker."""
    stored = load_pins().get(picker)
    return bool(stored) and verify_pin(pin, stored)
