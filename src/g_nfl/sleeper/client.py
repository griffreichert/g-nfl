"""Read-only client for the Sleeper public API (https://docs.sleeper.com).

No auth required; Sleeper asks for < 1000 calls/min. The public API is
**read-only**: pulling leagues/rosters/matchups/players works, but
roster moves (add/drop, lineups) go through Sleeper's private GraphQL
API, which is undocumented and needs an app auth token — out of scope.

The full NFL players blob is ~5MB and Sleeper asks that it be fetched
at most once per day, so it's cached on disk with a TTL.

Quick demo:

    uv run python -m g_nfl.sleeper.client <username>
"""

import json
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_CACHE_DIR = Path(__file__).parents[3] / "data" / "sleeper_cache"
PLAYERS_TTL_SECONDS = 24 * 3600

# fantasy-relevant positions for free-agent scans
SKILL_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


class SleeperClient:
    """Thin wrapper over the Sleeper public REST API."""

    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.session = requests.Session()

    def _get(self, path: str, **params: Any) -> Any:
        resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # -- core endpoints ------------------------------------------------

    def state(self) -> dict:
        """Current NFL state: season, week, season_type."""
        return self._get("/state/nfl")

    def user(self, username_or_id: str) -> dict:
        """User profile; use this to resolve a username to user_id."""
        return self._get(f"/user/{username_or_id}")

    def leagues(self, user_id: str, season: int | str) -> list[dict]:
        """All NFL leagues a user is in for a season."""
        return self._get(f"/user/{user_id}/leagues/nfl/{season}")

    def league(self, league_id: str) -> dict:
        return self._get(f"/league/{league_id}")

    def rosters(self, league_id: str) -> list[dict]:
        """All rosters in a league (player ids, starters, record)."""
        return self._get(f"/league/{league_id}/rosters")

    def league_users(self, league_id: str) -> list[dict]:
        """League members; maps owner_id -> display name."""
        return self._get(f"/league/{league_id}/users")

    def matchups(self, league_id: str, week: int) -> list[dict]:
        """Week matchups: points, starters, players per roster."""
        return self._get(f"/league/{league_id}/matchups/{week}")

    def transactions(self, league_id: str, week: int) -> list[dict]:
        """Waivers/trades/free-agent moves processed in a week."""
        return self._get(f"/league/{league_id}/transactions/{week}")

    def trending(
        self, kind: str = "add", lookback_hours: int = 24, limit: int = 25
    ) -> list[dict]:
        """Trending adds/drops across all of Sleeper: [{player_id, count}]."""
        if kind not in ("add", "drop"):
            raise ValueError("kind must be 'add' or 'drop'")
        return self._get(
            f"/players/nfl/trending/{kind}",
            lookback_hours=lookback_hours,
            limit=limit,
        )

    def players(self, refresh: bool = False) -> dict[str, dict]:
        """All NFL players keyed by sleeper player_id (~5MB blob).

        Disk-cached for 24h — Sleeper asks for at most one fetch/day.
        """
        cache = self.cache_dir / "players_nfl.json"
        if (
            not refresh
            and cache.exists()
            and time.time() - cache.stat().st_mtime < PLAYERS_TTL_SECONDS
        ):
            return json.loads(cache.read_text())
        data = self._get("/players/nfl")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
        return data

    # -- conveniences ---------------------------------------------------

    def user_leagues(
        self, username: str, season: int | str | None = None
    ) -> list[dict]:
        """Leagues by username; season defaults to the current league season."""
        if season is None:
            season = self.state()["league_season"]
        return self.leagues(self.user(username)["user_id"], season)

    def my_roster(self, league_id: str, username: str) -> dict:
        """The roster owned by `username` in a league."""
        user_id = self.user(username)["user_id"]
        for roster in self.rosters(league_id):
            if roster.get("owner_id") == user_id:
                return roster
        raise LookupError(f"{username} has no roster in league {league_id}")

    def free_agents(
        self, league_id: str, positions: set[str] | None = None
    ) -> list[dict]:
        """Active players not on any roster in the league.

        Returns player dicts (with `player_id` added) for `positions`
        (default: fantasy skill positions), so the caller can rank them
        with projections.
        """
        positions = positions or SKILL_POSITIONS
        rostered = {
            pid
            for roster in self.rosters(league_id)
            for pid in roster.get("players") or []
        }
        return [
            {"player_id": pid, **p}
            for pid, p in self.players().items()
            if pid not in rostered
            and p.get("position") in positions
            and p.get("active")
        ]


def main() -> None:
    """Demo: leagues + rosters for a username."""
    import argparse

    parser = argparse.ArgumentParser(description="Sleeper API demo")
    parser.add_argument("username")
    parser.add_argument("--season", default=None)
    args = parser.parse_args()

    client = SleeperClient()
    state = client.state()
    print(f"NFL state: season {state['season']} week {state['week']}")

    leagues = client.user_leagues(args.username, args.season)
    print(f"\n{args.username}: {len(leagues)} league(s)")
    for lg in leagues:
        print(f"\n=== {lg['name']} ({lg['league_id']}) — {lg['status']}")
        users = {
            u["user_id"]: u["display_name"]
            for u in client.league_users(lg["league_id"])
        }
        for r in client.rosters(lg["league_id"]):
            wins, losses = r["settings"].get("wins", 0), r["settings"].get("losses", 0)
            owner = users.get(r.get("owner_id"), "?")
            print(
                f"  {owner:20s} {wins}-{losses}  {len(r.get('players') or [])} players"
            )


if __name__ == "__main__":
    main()
