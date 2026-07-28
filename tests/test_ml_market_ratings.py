"""Tests for g_nfl.ml.market_ratings (#50): implied scores, the per-week
ridge-to-prior solver, the full trajectory, and its anti-leak contract."""

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from g_nfl.ml.market_ratings import (
    EMPTY_PRIOR,
    implied_team_scores,
    market_ratings,
    solve_week,
)


def _schedule(rows: list[tuple]) -> pl.DataFrame:
    """(season, week, home, away, location, spread_line, total_line) rows,
    REG games, unique game_ids assigned in order."""
    return pl.DataFrame(
        {
            "season": [r[0] for r in rows],
            "week": [r[1] for r in rows],
            "game_type": ["REG"] * len(rows),
            "game_id": [f"g{i}" for i in range(len(rows))],
            "home_team": [r[2] for r in rows],
            "away_team": [r[3] for r in rows],
            "location": [r[4] for r in rows],
            "spread_line": [r[5] for r in rows],
            "total_line": [r[6] for r in rows],
        }
    )


def _round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Circle-method round robin: len(teams)-1 rounds, each a perfect
    matching covering every pair exactly once across all rounds."""
    teams = list(teams)
    n = len(teams)
    rounds = []
    for _ in range(n - 1):
        pairs = [(teams[i], teams[n - 1 - i]) for i in range(n // 2)]
        rounds.append(pairs)
        teams.insert(1, teams.pop())
    return rounds


# ---- synthetic recovery (load-bearing) ----


def test_synthetic_recovery():
    """Round-robin schedule generated exactly from known off/def/hfa/mu;
    the solver must recover them from the implied lines alone.

    ``ovr_rating`` and ``hfa`` are pinned directly by a single game's
    (spread_line, total_line) once the other is known — no cross-week
    information needed — so they recover to numerical precision. The
    off/def *split* is a different story: each week only plays one game
    per team (standard football scheduling), so a single week's system
    is heavily underdetermined and the fixed-gain sequential solve
    settles into a bias from local off/def "consensus" averaging across
    repeated matchups, well short of the joint-least-squares answer a
    one-shot fit of all weeks at once would find. That's exactly the
    module docstring's "off/def is descriptive, ovr is trustworthy"
    trade-off, so off/def gets a looser (but still bounded) tolerance.
    """
    rng = np.random.default_rng(42)
    teams = [f"T{i}" for i in range(8)]
    off_raw = rng.normal(0, 2.0, size=8)
    def_raw = rng.normal(0, 2.0, size=8)
    c = (off_raw.mean() + def_raw.mean()) / 2
    off_true = off_raw - c
    def_true = def_raw - c
    hfa_true = 2.0
    mu = 22.0
    off_map = dict(zip(teams, off_true, strict=True))
    def_map = dict(zip(teams, def_true, strict=True))
    ovr_map = {t: off_map[t] + def_map[t] for t in teams}

    rounds = _round_robin(teams)
    rows = []
    week = 1
    for flip, _ in enumerate([0, 1]):  # double round robin: home/away swapped
        for rd in rounds:
            for i, (a, b) in enumerate(rd):
                home, away = (a, b) if (i + flip) % 2 == 0 else (b, a)
                total_line = (
                    2 * mu
                    + (off_map[home] - def_map[away])
                    + (off_map[away] - def_map[home])
                )
                spread_line = ovr_map[home] - ovr_map[away] + hfa_true
                rows.append((2023, week, home, away, "Home", spread_line, total_line))
            week += 1
    schedule = _schedule(rows)

    ratings = market_ratings(schedule, lam=0.1, hfa_lam=0.1, carryover=1.0)
    last_week = ratings["week"].max()
    final = ratings.filter(pl.col("week") == last_week).sort("team")
    truth = pl.DataFrame(
        {"team": teams, "off_true": off_true, "def_true": def_true}
    ).sort("team")
    cmp = final.join(truth, on="team")

    assert final["hfa"][0] == pytest.approx(hfa_true, abs=1e-2)
    assert (cmp["ovr_rating"] - (cmp["off_true"] + cmp["def_true"])).abs().max() < 0.02
    assert (cmp["off_rating"] - cmp["off_true"]).abs().max() < 0.6
    assert (cmp["def_rating"] - cmp["def_true"]).abs().max() < 0.6


# ---- centering invariance ----


def test_centering_invariance():
    teams = ["A", "B", "C", "D"]
    games = pl.DataFrame(
        {
            "home_team": ["A", "C"],
            "away_team": ["B", "D"],
            "y_home": [3.0, -1.0],
            "y_away": [-2.0, 4.0],
            "neutral": [False, False],
        }
    )
    prior_hfa, lam, hfa_lam = 1.5, 1.0, 1.0

    ratings, hfa = solve_week(games, teams, EMPTY_PRIOR, prior_hfa, lam, hfa_lam)

    # the (off += c, def += c) null direction is killed: mean(ovr) == 0
    assert ratings["ovr_rating"].mean() == pytest.approx(0.0, abs=1e-9)

    # re-derive the pre-centering beta the same way solve_week does, to
    # confirm subtracting one shared constant from off/def left every
    # fitted value (X @ beta) exactly unchanged
    idx = {t: i for i, t in enumerate(teams)}
    k = len(teams)
    X = np.zeros((4, 2 * k + 1))
    y = np.zeros(4)
    for row, (h, a, yh, ya) in enumerate(
        zip(
            games["home_team"],
            games["away_team"],
            games["y_home"],
            games["y_away"],
            strict=True,
        )
    ):
        X[2 * row, idx[h]] = 1.0
        X[2 * row, k + idx[a]] = -1.0
        X[2 * row, 2 * k] = 0.5
        y[2 * row] = yh
        X[2 * row + 1, idx[a]] = 1.0
        X[2 * row + 1, k + idx[h]] = -1.0
        X[2 * row + 1, 2 * k] = -0.5
        y[2 * row + 1] = ya
    L = np.diag([lam] * (2 * k) + [hfa_lam])
    p = np.zeros(2 * k + 1)
    p[2 * k] = prior_hfa
    raw_beta = np.linalg.solve(X.T @ X + L, X.T @ y + L @ p)

    ordered = ratings.sort("team")
    centered_beta = np.concatenate(
        [ordered["off_rating"].to_numpy(), ordered["def_rating"].to_numpy(), [hfa]]
    )
    np.testing.assert_allclose(X @ raw_beta, X @ centered_beta, atol=1e-9)


# ---- neutral site ----


def test_neutral_site_carries_no_hfa_info():
    teams = ["A", "B", "C", "D"]
    games = pl.DataFrame(
        {
            "home_team": ["A", "C"],
            "away_team": ["B", "D"],
            "y_home": [3.0, -1.0],
            "y_away": [-2.0, 4.0],
            "neutral": [True, True],
        }
    )
    _, hfa = solve_week(games, teams, EMPTY_PRIOR, prior_hfa=1.5, lam=1.0, hfa_lam=0.5)
    assert hfa == pytest.approx(1.5)


# ---- bye team holds prior ----


def test_bye_team_holds_prior():
    schedule = _schedule(
        [
            (2023, 1, "A", "B", "Home", 3.0, 45.0),
            (2023, 1, "C", "D", "Home", -2.0, 44.0),
            (2023, 2, "A", "C", "Home", 1.0, 46.0),  # B, D on bye this week
        ]
    )
    ratings = market_ratings(schedule, lam=5.0, hfa_lam=5.0, carryover=0.7)
    wk1 = ratings.filter(pl.col("week") == 1)
    wk2 = ratings.filter(pl.col("week") == 2)
    for team in ["B", "D"]:
        cols = ["off_rating", "def_rating", "ovr_rating"]
        assert_frame_equal(
            wk1.filter(pl.col("team") == team).select(cols),
            wk2.filter(pl.col("team") == team).select(cols),
        )


# ---- anti-leak ----


def test_future_week_does_not_leak():
    schedule = _schedule(
        [
            (2023, 1, "A", "B", "Home", 3.0, 45.0),
            (2023, 1, "C", "D", "Home", -2.0, 44.0),
            (2023, 2, "A", "C", "Home", 1.0, 46.0),
            (2023, 2, "B", "D", "Home", -0.5, 41.0),
            (2023, 3, "A", "D", "Home", 4.0, 50.0),
            (2023, 3, "B", "C", "Home", -3.0, 43.0),
        ]
    )
    perturbed = schedule.with_columns(
        pl.when(pl.col("week") == 3)
        .then(pl.col("spread_line") * 10 + 7)
        .otherwise(pl.col("spread_line"))
        .alias("spread_line"),
        pl.when(pl.col("week") == 3)
        .then(pl.col("total_line") + 50)
        .otherwise(pl.col("total_line"))
        .alias("total_line"),
    )
    base = market_ratings(schedule, lam=2.0, hfa_lam=2.0, carryover=0.7)
    pert = market_ratings(perturbed, lam=2.0, hfa_lam=2.0, carryover=0.7)

    assert_frame_equal(
        base.filter(pl.col("week") <= 2).sort("week", "team"),
        pert.filter(pl.col("week") <= 2).sort("week", "team"),
    )
    # sanity: week 3 actually did change
    assert (
        not base.filter(pl.col("week") == 3)
        .sort("team")
        .equals(pert.filter(pl.col("week") == 3).sort("team"))
    )


# ---- null lines ----


def test_null_lines_dropped_without_crashing():
    schedule = _schedule(
        [
            (2023, 1, "A", "B", "Home", 3.0, 45.0),
            (2023, 1, "C", "D", "Home", None, 44.0),  # null spread_line: dropped
            (2023, 2, "A", "C", "Home", 1.0, 46.0),
            (2023, 2, "B", "D", "Home", -0.5, 41.0),
        ]
    )
    games = implied_team_scores(schedule)
    assert games.height == 3  # the null-line game is dropped, the rest survive
    assert set(games["game_id"].to_list()) == {"g0", "g2", "g3"}

    # C and D are still in the season's team universe (they play valid games
    # in week 2) but had no equation in week 1 -> held at the week-1 prior (0)
    ratings = market_ratings(schedule, lam=2.0, hfa_lam=2.0, carryover=0.7)
    assert ratings.height > 0  # doesn't crash
    wk1 = ratings.filter(pl.col("week") == 1)
    for team in ["C", "D"]:
        row = wk1.filter(pl.col("team") == team)
        assert row["off_rating"][0] == pytest.approx(0.0)
        assert row["def_rating"][0] == pytest.approx(0.0)
