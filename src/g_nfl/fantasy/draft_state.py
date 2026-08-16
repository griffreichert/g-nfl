"""Who has already been drafted, and where that fact survives (issue #79).

A JSON file on disk, not session state and not a database. Three reasons, all
about draft day:

- **A refresh mid-draft must not lose 40 picks.** Streamlit's session state does
  not survive one, so it cannot hold this.
- **Wifi must not be able to break the board.** Supabase (#81) is the store for
  everything the app *reads*; draft state is the one thing it writes, at the
  worst possible moment for a network round trip.
- The file is trivially inspectable and deletable when the draft is over.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path("data/fantasy/draft_state.json")


def load_drafted(path: Path = DEFAULT_PATH) -> set[str]:
    """The ``gsis_id`` set already off the board. Missing file means none."""
    if not path.exists():
        return set()
    return set(json.loads(path.read_text())["drafted"])


def save_drafted(drafted: set[str], path: Path = DEFAULT_PATH) -> None:
    """Persist the set, creating the directory on the way."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"drafted": sorted(drafted)}, indent=2))


def toggle(drafted: set[str], gsis_id: str, *, is_drafted: bool) -> set[str]:
    """Add or remove one player, returning a new set."""
    return drafted | {gsis_id} if is_drafted else drafted - {gsis_id}
