#!/usr/bin/env python3
"""Generate the PICKER_PINS value for the picks API (#60).

**Dormant.** The site signs in with one shared passphrase (`APP_PASSPHRASE`),
so `PICKER_PINS` is read by nothing today. `src/g_nfl/api/pins.py` explains what
to change to switch back to per-picker PINs; this script is what feeds it.

    uv run python scripts/make_pin.py Griffin 1234 Harry 5678

Prints a JSON object to paste into `.env` and into Render's environment. PINs
are hashed with PBKDF2, so the environment never holds one in the clear and a
leaked env var does not hand anyone the room's PINs.

Re-run with every picker each time: the output replaces the variable rather
than adding to it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1] / "src"))

from g_nfl.api.pins import hash_pin  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    if not args or len(args) % 2:
        sys.exit("usage: make_pin.py <picker> <pin> [<picker> <pin> ...]")

    pairs = zip(args[::2], args[1::2], strict=True)
    print(json.dumps({picker: hash_pin(pin) for picker, pin in pairs}))


if __name__ == "__main__":
    main()
