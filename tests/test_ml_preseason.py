"""Tests for the preseason block: what a team is worth before it has
played a snap.

Headline guard: a week-1 game must not come back with every feature
null. That was the bug this module exists to fix -- the matrix lags a
week, week 0 has no row, and the model answered every week-1 game with
one constant.
"""

import polars as pl
import pytest

from g_nfl.ml.features.preseason import (
    ROUND_VALUE,
    _draft_capital,
    _prior_season_results,
    _snap_retention,
    add_preseason,
    preseason_features,
)
from g_nfl.ml.features.registry import get_feature_set
from g_nfl.utils.config import HFA

TEAMS = ["KC", "BUF", "SF", "PHI"]


def _schedule(season: int, spreads: dict[tuple[str, str], float]) -> list[dict]:
    """One week per matchup so weeks stay distinct and coaches carry."""
    rows = []
    for week, ((home, away), spread) in enumerate(spreads.items(), start=1):
        rows.append(
            {
                "game_id": f"{season}_{week:02d}_{away}_{home}",
                "season": season,
                "week": week,
                "game_type": "REG",
                "home_team": home,
                "away_team": away,
                "home_score": 24,
                "away_score": 17,
                "spread_line": spread,
                "result": 7,
                "home_qb_id": f"qb_{home}",
                "away_qb_id": f"qb_{away}",
                "home_coach": f"coach_{home}",
                "away_coach": f"coach_{away}",
            }
        )
    return rows


@pytest.fixture
def schedule() -> pl.DataFrame:
    """Two seasons, so 2024 rows have a 2023 prior behind them."""
    rows = _schedule(2023, {("KC", "BUF"): 6.0, ("SF", "PHI"): 2.0}) + _schedule(
        2024, {("KC", "BUF"): 3.0, ("SF", "PHI"): 1.0}
    )
    return pl.DataFrame(rows)


@pytest.fixture
def pbp(pbp_sample) -> pl.DataFrame:
    """The real 2023 sample, plus a copy stamped 2024, so a 2024 row has
    a prior season behind it. Real pbp beats a hand-built frame here --
    `play_features` reads two dozen columns and the point of these tests
    is the preseason logic, not the play filter.

    ``posteam`` is remapped onto the four fixture teams so the QB-change
    check has a prior passer for each.
    """
    real = pbp_sample["posteam"].drop_nulls().unique().sort().to_list()
    onto = {team: TEAMS[i % len(TEAMS)] for i, team in enumerate(real)}
    remap = pbp_sample.with_columns(
        posteam=pl.col("posteam").replace(onto),
        defteam=pl.col("defteam").replace(onto),
    ).with_columns(passer_player_id=pl.concat_str(pl.lit("qb_"), pl.col("posteam")))
    return pl.concat([remap, remap.with_columns(season=pl.col("season") + 1)])


def test_market_rating_removes_hfa(schedule):
    """A home favourite of ``spread`` is worth ``spread - HFA`` on the
    day, and the away side the negation."""
    res = _prior_season_results(schedule).filter(pl.col("season") == 2024)
    kc = res.filter(pl.col("team") == "KC")["pre_mkt_rating"].item()
    buf = res.filter(pl.col("team") == "BUF")["pre_mkt_rating"].item()
    assert kc == pytest.approx(6.0 - HFA)
    assert buf == pytest.approx(HFA - 6.0)


def test_prior_season_only(schedule):
    """The 2024 row must describe 2023. KC's 2024 line is 3.0 and its
    2023 line 6.0, so a rating built off 2024 would give 3.0 - HFA."""
    res = _prior_season_results(schedule)
    kc_2024 = res.filter((pl.col("team") == "KC") & (pl.col("season") == 2024))
    assert kc_2024["pre_mkt_rating"].item() == pytest.approx(6.0 - HFA)
    # the earliest season has no prior, so it gets no row at all
    assert res.filter(pl.col("season") == 2023).is_empty()


def test_qb_and_coach_change_detected(schedule, pbp):
    """Swap KC's week-1 2024 starter and coach; both flags must fire,
    and only for KC."""
    changed = schedule.with_columns(
        home_qb_id=pl.when((pl.col("season") == 2024) & (pl.col("home_team") == "KC"))
        .then(pl.lit("qb_backup"))
        .otherwise(pl.col("home_qb_id")),
        home_coach=pl.when((pl.col("season") == 2024) & (pl.col("home_team") == "KC"))
        .then(pl.lit("coach_new"))
        .otherwise(pl.col("home_coach")),
    )
    f = preseason_features(pbp, changed).filter(pl.col("season") == 2024)
    kc = f.filter(pl.col("team") == "KC")
    assert kc["pre_qb_change"].item() == 1
    assert kc["pre_coach_change"].item() == 1
    assert f.filter(pl.col("team") == "SF")["pre_qb_change"].item() == 0
    assert f.filter(pl.col("team") == "SF")["pre_coach_change"].item() == 0


def test_draft_capital_weights_rounds():
    draft = pl.DataFrame(
        [
            {"team": "KC", "season": 2024, "round": 1, "pick": 10},
            {"team": "KC", "season": 2024, "round": 7, "pick": 240},
            {"team": "BUF", "season": 2024, "round": 2, "pick": 55},
        ]
    )
    cap = _draft_capital(draft)
    kc = cap.filter(pl.col("team") == "KC")
    assert kc["pre_draft_value"].item() == pytest.approx(
        ROUND_VALUE[1] + ROUND_VALUE[7]
    )
    assert kc["pre_first_rounders"].item() == 1
    assert kc["pre_top50_picks"].item() == 1
    assert cap.filter(pl.col("team") == "BUF")["pre_top50_picks"].item() == 0


def test_snap_retention_is_snap_weighted():
    """A departed starter costs more retention than a departed backup."""
    snaps = pl.DataFrame(
        [
            {
                "team": "KC",
                "season": 2023,
                "game_type": "REG",
                "pfr_player_id": pid,
                "offense_snaps": n,
                "defense_snaps": 0,
            }
            for pid, n in [("starter", 900), ("backup", 100)]
        ]
    )
    rosters = pl.DataFrame(
        [
            {
                "team": "KC",
                "season": 2024,
                "week": 1,
                "pfr_id": "starter",
                "gsis_id": "a",
            },
        ]
    )
    kept_starter = _snap_retention(snaps, rosters)["pre_snap_retention"].item()
    assert kept_starter == pytest.approx(0.9)

    rosters_backup = rosters.with_columns(pfr_id=pl.lit("backup"))
    kept_backup = _snap_retention(snaps, rosters_backup)["pre_snap_retention"].item()
    assert kept_backup == pytest.approx(0.1)


def test_crosswalk_recovers_missing_pfr_id():
    """Rosters with a null ``pfr_id`` still count when ``players`` maps
    the player's ``gsis_id`` across."""
    snaps = pl.DataFrame(
        [
            {
                "team": "KC",
                "season": 2023,
                "game_type": "REG",
                "pfr_player_id": "starter",
                "offense_snaps": 500,
                "defense_snaps": 0,
            }
        ]
    )
    rosters = pl.DataFrame(
        [{"team": "KC", "season": 2024, "week": 1, "pfr_id": None, "gsis_id": "gsis1"}],
        schema={
            "team": pl.String,
            "season": pl.Int64,
            "week": pl.Int64,
            "pfr_id": pl.String,
            "gsis_id": pl.String,
        },
    )
    players = pl.DataFrame([{"gsis_id": "gsis1", "pfr_id": "starter"}])

    assert _snap_retention(snaps, rosters)["pre_snap_retention"].item() == 0.0
    with_map = _snap_retention(snaps, rosters, players)
    assert with_map["pre_snap_retention"].item() == pytest.approx(1.0)


def test_add_preseason_makes_diffs(schedule, pbp):
    pre = preseason_features(pbp, schedule)
    matrix = schedule.filter(pl.col("season") == 2024).select(
        "game_id", "season", "week", "home_team", "away_team", "result", "spread_line"
    )
    out = add_preseason(matrix, pre)

    kc_game = out.filter(pl.col("home_team") == "KC")
    assert kc_game["pre_diff_mkt_rating"].item() == pytest.approx(
        kc_game["home_pre_mkt_rating"].item() - kc_game["away_pre_mkt_rating"].item()
    )
    assert out.height == matrix.height


def test_week_one_features_are_not_all_null(schedule, pbp):
    """The whole point: a week-1 row must carry real numbers.

    The in-season block is null there by construction, so if the
    preseason block were absent the model would see nothing at all.
    """
    pre = preseason_features(pbp, schedule)
    matrix = schedule.filter((pl.col("season") == 2024) & (pl.col("week") == 1)).select(
        "game_id", "season", "week", "home_team", "away_team", "result", "spread_line"
    )
    out = add_preseason(matrix, pre)
    pre_cols = [c for c in out.columns if "pre_" in c]
    assert pre_cols
    assert all(out[c].null_count() == 0 for c in pre_cols)


def test_v3_early_selects_the_block_and_v1_ignores_it(schedule, pbp):
    """``v1_team`` must mean the same thing whether or not the matrix was
    built with the preseason block attached."""
    pre = preseason_features(pbp, schedule)
    matrix = schedule.filter(pl.col("season") == 2024).select(
        "game_id",
        "season",
        "week",
        "home_team",
        "away_team",
        "result",
        "spread_line",
        pl.lit(0.1).alias("home_epa_mean_season"),
    )
    with_pre = add_preseason(matrix, pre)

    v1 = get_feature_set("v1_team")
    assert v1.columns(with_pre) == v1.columns(matrix) == ["home_epa_mean_season"]

    early = get_feature_set("v3_early").columns(with_pre)
    assert "home_epa_mean_season" in early
    assert "pre_diff_mkt_rating" in early
    assert "week" in early

    with pytest.raises(ValueError, match="preseason=True"):
        get_feature_set("v3_early").columns(matrix)


def test_v4_lean_is_v3_without_the_rolling_window(schedule, pbp):
    """The rolling family measured as noise (see the registry comment), so
    ``v4_early_lean`` drops it and keeps everything else v3 selects."""
    pre = preseason_features(pbp, schedule)
    matrix = add_preseason(
        schedule.filter(pl.col("season") == 2024).select(
            "game_id",
            "season",
            "week",
            "home_team",
            "away_team",
            "result",
            "spread_line",
            pl.lit(0.1).alias("home_epa_mean_season"),
            pl.lit(0.2).alias("home_epa_mean_last_4w"),
            pl.lit(0.3).alias("home_epa_mean_carry"),
        ),
        pre,
    )

    v3 = get_feature_set("v3_early").columns(matrix)
    v4 = get_feature_set("v4_early_lean").columns(matrix)

    assert "home_epa_mean_last_4w" in v3
    assert not [c for c in v4 if c.endswith("_last_4w")]
    assert set(v4) == set(v3) - {"home_epa_mean_last_4w"}
    for keep in ("home_epa_mean_season", "home_epa_mean_carry", "pre_diff_mkt_rating"):
        assert keep in v4
