"""Tests for L4 availability-weighted unit value lost (#39 lever 2).

Headline guards: the expected-loss arithmetic (Out=0.0/Doubtful=0.2/
Questionable=0.7 weighting on a hand-computed lagged snap share), QB
exclusion, no-report -> 0, and anti-leak (future weeks can't move a
past week's feature).
"""

import polars as pl
import pytest

from g_nfl.ml.features import build_features
from g_nfl.ml.features.availability import add_availability, team_week_availability


def _snaps(rows: list[dict]) -> pl.DataFrame:
    """Minimal snap_counts. rows: team, week, player, pos, off_pct,
    def_pct (season 2023 REG unless overridden)."""
    return pl.DataFrame(
        [
            {
                "game_type": "REG",
                "season": r.get("season", 2023),
                "week": r["week"],
                "team": r["team"],
                "pfr_player_id": r["player"],
                "position": r["pos"],
                "offense_pct": r.get("off_pct", 0.0),
                "defense_pct": r.get("def_pct", 0.0),
            }
            for r in rows
        ]
    )


def _injuries(rows: list[dict]) -> pl.DataFrame:
    """rows: team, week, gsis_id, pos, status (season 2023 REG)."""
    return pl.DataFrame(
        [
            {
                "season": r.get("season", 2023),
                "game_type": "REG",
                "team": r["team"],
                "week": r["week"],
                "gsis_id": r["gsis_id"],
                "position": r["pos"],
                "report_status": r["status"],
            }
            for r in rows
        ]
    )


def _players(rows: list[tuple[str, str]]) -> pl.DataFrame:
    """rows: (gsis_id, pfr_id)."""
    return pl.DataFrame(
        {"gsis_id": [r[0] for r in rows], "pfr_id": [r[1] for r in rows]}
    )


# p1: WR (skill), week1 offense_pct=0.8 -> lagged share entering week2 = 0.8
# p2: CB (secondary), week1 defense_pct=0.6 -> lagged share entering week2 = 0.6
# p3: T (OL), week1 offense_pct=0.5, never reported -> control (always 0 loss)
SNAPS = _snaps(
    [
        {"team": "KC", "week": 1, "player": "pfr_p1", "pos": "WR", "off_pct": 0.8},
        {"team": "KC", "week": 2, "player": "pfr_p1", "pos": "WR", "off_pct": 0.1},
        {"team": "KC", "week": 1, "player": "pfr_p2", "pos": "CB", "def_pct": 0.6},
        {"team": "KC", "week": 2, "player": "pfr_p2", "pos": "CB", "def_pct": 0.9},
        {"team": "KC", "week": 1, "player": "pfr_p3", "pos": "T", "off_pct": 0.5},
        {"team": "KC", "week": 2, "player": "pfr_p3", "pos": "T", "off_pct": 0.5},
        # p4: QB, week1 high snap share, reported Out week2 -> must not
        # contribute anywhere (lever 1's territory, not lever 2's)
        {"team": "KC", "week": 1, "player": "pfr_p4", "pos": "QB", "off_pct": 1.0},
        {"team": "KC", "week": 2, "player": "pfr_p4", "pos": "QB", "off_pct": 1.0},
    ]
)
PLAYERS = _players(
    [("gsis_p1", "pfr_p1"), ("gsis_p2", "pfr_p2"), ("gsis_p4", "pfr_p4")]
)


def _injuries_week2(extra: list[dict] | None = None) -> pl.DataFrame:
    rows = [
        {"team": "KC", "week": 2, "gsis_id": "gsis_p1", "pos": "WR", "status": "Out"},
        {
            "team": "KC",
            "week": 2,
            "gsis_id": "gsis_p2",
            "pos": "CB",
            "status": "Questionable",
        },
        {"team": "KC", "week": 2, "gsis_id": "gsis_p4", "pos": "QB", "status": "Out"},
    ]
    return _injuries(rows + (extra or []))


def _row(out: pl.DataFrame, team: str, week: int) -> dict:
    return out.filter((pl.col("team") == team) & (pl.col("week") == week)).row(
        0, named=True
    )


def test_out_weighting_uses_lagged_share():
    out = team_week_availability(SNAPS, _injuries_week2(), PLAYERS)
    r = _row(out, "KC", 2)
    # p1 lagged share entering week 2 = week 1's only value = 0.8;
    # Out -> p_play=0.0 -> loss = (1 - 0.0) * 0.8 = 0.8
    assert r["avail_loss_skill"] == pytest.approx(0.8)


def test_questionable_weighting():
    out = team_week_availability(SNAPS, _injuries_week2(), PLAYERS)
    r = _row(out, "KC", 2)
    # p2 lagged share entering week 2 = 0.6; Questionable -> p_play=0.7
    # -> loss = 0.3 * 0.6 = 0.18
    assert r["avail_loss_sec"] == pytest.approx(0.3 * 0.6)


def test_qb_excluded_entirely():
    out = team_week_availability(SNAPS, _injuries_week2(), PLAYERS)
    r = _row(out, "KC", 2)
    assert "avail_loss_qb" not in out.columns
    # QB's Out status must not leak onto any of the four tracked units
    for col in ("avail_loss_ol", "avail_loss_skill", "avail_loss_front7"):
        assert col not in ("avail_loss_qb",)  # sanity the col name itself is gone
    assert r["avail_loss_ol"] == pytest.approx(0.0)  # p3 (OL) never reported
    assert r["avail_loss_front7"] == pytest.approx(0.0)


def test_no_report_stays_zero():
    # team_week_availability only emits rows where something was
    # reported (sparse, same convention as team_week_injuries); a
    # team-week with nothing designated gets 0 after add_availability's
    # left join, never a missing/null feature.
    matrix = pl.DataFrame(
        {
            "game_id": ["g1"],
            "season": [2023],
            "week": [1],
            "home_team": ["KC"],
            "away_team": ["X"],
        }
    )
    out = add_availability(matrix, SNAPS, _injuries_week2(), PLAYERS)
    r = out.row(0, named=True)
    for col in (
        "home_avail_loss_ol",
        "home_avail_loss_skill",
        "home_avail_loss_sec",
        "home_avail_loss_front7",
    ):
        assert r[col] == pytest.approx(0.0)


def test_first_week_no_history_falls_back_to_zero_without_prior_season():
    # p1's week-1 lagged share has no history at all (no prior season
    # loaded) -> 0, so an (impossible in this fixture, but checked
    # directly) week-1 report would score a zero-value loss.
    lagged_only = team_week_availability(
        SNAPS,
        _injuries(
            [
                {
                    "team": "KC",
                    "week": 1,
                    "gsis_id": "gsis_p1",
                    "pos": "WR",
                    "status": "Out",
                }
            ]
        ),
        PLAYERS,
    )
    r = _row(lagged_only, "KC", 1)
    assert r["avail_loss_skill"] == pytest.approx(0.0)


def test_prior_season_fallback_when_loaded():
    snaps_two_seasons = pl.concat(
        [
            SNAPS,
            _snaps(
                [
                    {
                        "team": "KC",
                        "season": 2022,
                        "week": 1,
                        "player": "pfr_p1",
                        "pos": "WR",
                        "off_pct": 0.4,
                    },
                    {
                        "team": "KC",
                        "season": 2022,
                        "week": 2,
                        "player": "pfr_p1",
                        "pos": "WR",
                        "off_pct": 0.6,
                    },
                ]
            ),
        ],
        how="vertical_relaxed",
    )
    out = team_week_availability(
        snaps_two_seasons,
        _injuries(
            [
                {
                    "team": "KC",
                    "week": 1,
                    "gsis_id": "gsis_p1",
                    "pos": "WR",
                    "status": "Out",
                }
            ]
        ),
        PLAYERS,
    )
    r = _row(out, "KC", 1)
    # 2023 week 1 has no in-season history -> falls back to 2022's full
    # season mean for p1: mean(0.4, 0.6) = 0.5; Out -> loss = 0.5
    assert r["avail_loss_skill"] == pytest.approx(0.5)


def test_future_weeks_do_not_leak():
    """Perturb week-3 snap shares and add a week-3 injury report; weeks
    1-2 features must stay identical (own-week injury join is fine, lag
    on the snap-share value is not up for negotiation)."""
    snaps_3wk = pl.concat(
        [
            SNAPS,
            _snaps(
                [
                    {
                        "team": "KC",
                        "week": 3,
                        "player": "pfr_p1",
                        "pos": "WR",
                        "off_pct": 0.3,
                    }
                ]
            ),
        ],
        how="vertical_relaxed",
    )
    inj_3wk = _injuries_week2()
    base = team_week_availability(snaps_3wk, inj_3wk, PLAYERS)

    perturbed_snaps = snaps_3wk.with_columns(
        pl.when(pl.col("week") == 3)
        .then(pl.lit(0.99))
        .otherwise(pl.col("offense_pct"))
        .alias("offense_pct")
    )
    perturbed_inj = pl.concat(
        [
            inj_3wk,
            _injuries(
                [
                    {
                        "team": "KC",
                        "week": 3,
                        "gsis_id": "gsis_p1",
                        "pos": "WR",
                        "status": "Out",
                    }
                ]
            ),
        ],
        how="vertical_relaxed",
    )
    pert = team_week_availability(perturbed_snaps, perturbed_inj, PLAYERS)

    from polars.testing import assert_frame_equal

    assert_frame_equal(
        base.filter(pl.col("week") != 3).sort("team", "week"),
        pert.filter(pl.col("week") != 3).sort("team", "week"),
    )
    # sanity: week 3 actually changed (new report + perturbed share)
    assert pert.filter(pl.col("week") == 3).height > 0


# ---- add_availability / build_features (real fixture) ----


def test_add_availability_toggle_and_columns(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    base = build_features(pbp_sample, schedule_sample)
    assert not any(
        c.startswith(("home_avail_loss", "away_avail_loss")) for c in base.columns
    )

    out = build_features(
        pbp_sample,
        schedule_sample,
        snaps=SNAPS,
        players=PLAYERS,
        availability=_injuries_week2(),
    )
    # availability carries its own injuries frame (qb_change convention),
    # independent of the L3 ``injuries`` lever -- the avail_loss cols are
    # exactly what's added.
    added = set(out.columns) - set(base.columns)
    assert added == {
        f"{side}_avail_loss_{u}"
        for side in ("home", "away")
        for u in ("ol", "skill", "front7", "sec")
    }

    # week 2: KC is away (2023_02_KC_JAX)
    kc_wk2 = out.filter(
        (pl.col("week") == 2)
        & ((pl.col("home_team") == "KC") | (pl.col("away_team") == "KC"))
    ).row(0, named=True)
    side = "home" if kc_wk2["home_team"] == "KC" else "away"
    other = "away" if side == "home" else "home"
    assert kc_wk2[f"{side}_avail_loss_skill"] == pytest.approx(0.8)
    assert kc_wk2[f"{side}_avail_loss_sec"] == pytest.approx(0.3 * 0.6)
    assert kc_wk2[f"{other}_avail_loss_skill"] == pytest.approx(
        0.0
    )  # opponent untouched


def test_toggle_off_is_byte_identical(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    from polars.testing import assert_frame_equal

    base = build_features(pbp_sample, schedule_sample)
    off = build_features(pbp_sample, schedule_sample, availability=None)
    assert_frame_equal(base, off)


def test_add_availability_matches_direct_call(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    matrix = build_features(pbp_sample, schedule_sample)
    out = add_availability(matrix, SNAPS, _injuries_week2(), PLAYERS)
    direct = team_week_availability(SNAPS, _injuries_week2(), PLAYERS)

    kc_direct = direct.filter((pl.col("team") == "KC") & (pl.col("week") == 2)).row(
        0, named=True
    )
    kc_row = out.filter(pl.col("game_id") == "2023_02_KC_JAX").row(0, named=True)
    side = "home" if kc_row["home_team"] == "KC" else "away"
    assert kc_row[f"{side}_avail_loss_skill"] == pytest.approx(
        kc_direct["avail_loss_skill"]
    )
