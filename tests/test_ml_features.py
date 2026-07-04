"""Tests for g_nfl.ml.features (#9): play features, team-week aggregates,
windows, the game matrix, anti-leakage, and the feature-set registry."""

import polars as pl
import pytest
from polars.testing import assert_frame_equal, assert_series_equal

from g_nfl.ml.features import build_features
from g_nfl.ml.features.carryover import carryover_blend
from g_nfl.ml.features.matrix import META_COLS, build_game_matrix
from g_nfl.ml.features.opponent import (
    STATS,
    add_opponent_ratings,
    fit_opponent_ratings,
    team_games_frame,
)
from g_nfl.ml.features.plays import (
    EPA_SPLIT_COLS,
    HAVOC_COLS,
    ID_COLS,
    PLAY_FEATURE_COLS,
    add_play_features,
    filter_plays,
    play_features,
)
from g_nfl.ml.features.registry import get_feature_set
from g_nfl.ml.features.team_week import team_week_stats
from g_nfl.ml.features.windows import add_windows
from g_nfl.utils.config import DEFAULT_WIN_PROB

# ---- pipeline stages built once from the pbp fixture ----


@pytest.fixture(scope="module")
def filtered(pbp_sample: pl.DataFrame) -> pl.DataFrame:
    return filter_plays(pbp_sample)


@pytest.fixture(scope="module")
def feats(filtered: pl.DataFrame) -> pl.DataFrame:
    return add_play_features(filtered)


@pytest.fixture(scope="module")
def plays(pbp_sample: pl.DataFrame) -> pl.DataFrame:
    return play_features(pbp_sample)


@pytest.fixture(scope="module")
def weekly(plays: pl.DataFrame) -> pl.DataFrame:
    return team_week_stats(plays)


@pytest.fixture(scope="module")
def reg_schedule(schedule_sample: pl.DataFrame) -> pl.DataFrame:
    return schedule_sample.filter(pl.col("game_type") == "REG")


@pytest.fixture(scope="module")
def windowed(weekly: pl.DataFrame, reg_schedule: pl.DataFrame) -> pl.DataFrame:
    return add_windows(weekly, reg_schedule)


@pytest.fixture(scope="module")
def matrix(windowed: pl.DataFrame, reg_schedule: pl.DataFrame) -> pl.DataFrame:
    return build_game_matrix(windowed, reg_schedule)


# ---- plays ----


def test_filter_plays(pbp_sample: pl.DataFrame, filtered: pl.DataFrame):
    assert 0 < filtered.height < pbp_sample.height
    assert set(filtered["play_type"].unique()) <= {"run", "pass"}
    assert filtered["season_type"].unique().to_list() == ["REG"]
    assert filtered["wp"].min() >= DEFAULT_WIN_PROB
    assert filtered["wp"].max() <= 1 - DEFAULT_WIN_PROB


def test_havoc_flags_disruptive_plays(feats: pl.DataFrame):
    sacks = feats.filter(pl.col("sack") == 1)
    assert sacks.height > 0
    assert sacks["havoc"].all()

    clean = feats.filter(pl.all_horizontal([pl.col(c) == 0 for c in HAVOC_COLS]))
    assert clean.height > 0
    assert not clean["havoc"].any()


def test_pass_rush_yards_split(feats: pl.DataFrame):
    passes = feats.filter(pl.col("pass_attempt") == 1)
    assert (passes["pass_yards"] == passes["yards_gained"]).all()
    non_passes = feats.filter(pl.col("pass_attempt") == 0)
    assert non_passes["pass_yards"].null_count() == non_passes.height

    rushes = feats.filter(pl.col("rush_attempt") == 1)
    assert (rushes["rush_yards"] == rushes["yards_gained"]).all()


def test_explosive_play_thresholds(feats: pl.DataFrame):
    explosive_pass = feats.filter(pl.col("explosive_pass"))
    assert explosive_pass.height > 0
    assert (explosive_pass["yards_gained"] >= 15).all()
    assert (explosive_pass["play_type"] == "pass").all()

    explosive_rush = feats.filter(pl.col("explosive_rush"))
    assert explosive_rush.height > 0
    assert (explosive_rush["yards_gained"] >= 10).all()
    assert (explosive_rush["play_type"] == "run").all()

    assert (
        feats["explosive_play"] == (feats["explosive_pass"] | feats["explosive_rush"])
    ).all()


def test_rate_columns_rescaled(filtered: pl.DataFrame, feats: pl.DataFrame):
    assert_series_equal(feats["cpoe"], filtered["cpoe"] / 100)
    assert_series_equal(feats["pass_oe"], filtered["pass_oe"] / 100)
    assert feats["cpoe"].abs().max() <= 1.0


def test_play_features_columns(plays: pl.DataFrame):
    assert plays.columns == ID_COLS + PLAY_FEATURE_COLS


def test_epa_splits_toggle(pbp_sample: pl.DataFrame):
    base = play_features(pbp_sample)
    assert not any("pass_epa" == c for c in base.columns)

    split = play_features(pbp_sample, epa_splits=True)
    assert split.columns == ID_COLS + PLAY_FEATURE_COLS + EPA_SPLIT_COLS
    assert split.filter(pl.col("pass_epa").is_not_null()).height > 0
    assert split.filter(pl.col("rush_epa").is_not_null()).height > 0
    # a play is pass_epa or rush_epa, never both
    assert (
        split.filter(
            pl.col("pass_epa").is_not_null() & pl.col("rush_epa").is_not_null()
        ).height
        == 0
    )


# ---- team_week ----


def test_team_week_offense_aggregates(plays: pl.DataFrame, weekly: pl.DataFrame):
    kc_w1 = plays.filter((pl.col("posteam") == "KC") & (pl.col("week") == 1))
    row = weekly.filter((pl.col("team") == "KC") & (pl.col("week") == 1))
    assert row.height == 1
    assert row["plays"][0] == kc_w1.height
    assert row["epa"][0] == pytest.approx(kc_w1["epa"].sum())
    assert row["epa_mean"][0] == pytest.approx(kc_w1["epa"].mean())


def test_team_week_defense_mirrors_opponent_offense(
    weekly: pl.DataFrame, reg_schedule: pl.DataFrame
):
    game = reg_schedule.filter(
        (pl.col("week") == 1)
        & ((pl.col("home_team") == "KC") | (pl.col("away_team") == "KC"))
    )
    home, away = game["home_team"][0], game["away_team"][0]
    opponent = away if home == "KC" else home

    kc_def_epa = weekly.filter((pl.col("team") == "KC") & (pl.col("week") == 1))[
        "epa_def"
    ][0]
    opp_off_epa = weekly.filter((pl.col("team") == opponent) & (pl.col("week") == 1))[
        "epa"
    ][0]
    assert kc_def_epa == pytest.approx(opp_off_epa)


def test_team_week_one_row_per_team_week(weekly: pl.DataFrame):
    keys = weekly.select("team", "season", "week")
    assert keys.height == keys.unique().height


# ---- windows ----


def test_rolling_and_season_sums(weekly: pl.DataFrame, windowed: pl.DataFrame):
    kc = weekly.filter(pl.col("team") == "KC").sort("week")
    assert kc["week"].to_list() == [1, 2, 3, 4, 5]

    kc_w5 = windowed.filter((pl.col("team") == "KC") & (pl.col("week") == 5))
    assert kc_w5["epa_last_4w"][0] == pytest.approx(
        kc.filter(pl.col("week") > 1)["epa"].sum()
    )
    assert kc_w5["epa_season"][0] == pytest.approx(kc["epa"].sum())


def test_windows_full_team_week_grid(windowed: pl.DataFrame, weekly: pl.DataFrame):
    n_teams = weekly["team"].n_unique()
    assert windowed.height == n_teams * 5  # every team gets all 5 fixture weeks


def test_forward_fill_on_bye_weeks():
    # team misses week 3; windowed stats must carry week 2 forward
    weekly = pl.DataFrame(
        {
            "team": ["AAA"] * 3,
            "season": [2023] * 3,
            "week": [1, 2, 4],
            "epa": [1.0, 2.0, 4.0],
        }
    )
    schedule = pl.DataFrame({"season": [2023] * 4, "week": [1, 2, 3, 4]})
    windowed = add_windows(weekly, schedule, rolling_weeks=2)

    bye = windowed.filter(pl.col("week") == 3)
    assert bye["epa_season"][0] == pytest.approx(3.0)
    assert bye["epa_last_2w"][0] == pytest.approx(3.0)
    assert bye["epa"][0] is None  # raw weekly stat stays null on the bye

    week4 = windowed.filter(pl.col("week") == 4)
    assert week4["epa_season"][0] == pytest.approx(7.0)
    # rolling window spans games played, skipping the bye: weeks 2 + 4
    assert week4["epa_last_2w"][0] == pytest.approx(6.0)


# ---- windows: L2 time decay ----


def test_decay_emits_ewm_drops_volume(weekly: pl.DataFrame, reg_schedule: pl.DataFrame):
    decayed = add_windows(weekly, reg_schedule, half_life=3.0)
    stat_cols = [c for c in decayed.columns if c not in ("team", "season", "week")]
    assert stat_cols  # something came through
    assert all(c.endswith("_ewm") for c in stat_cols)
    # only rate (_mean) stats survive; raw volume sums are gone
    assert all("_mean" in c for c in stat_cols)
    assert "epa_mean_ewm" in stat_cols
    assert "epa_ewm" not in stat_cols  # the raw volume sum was dropped


def test_decay_first_game_equals_raw(weekly: pl.DataFrame, reg_schedule: pl.DataFrame):
    # EWMA of a single observation is that observation
    decayed = add_windows(weekly, reg_schedule, half_life=3.0)
    kc_w1_raw = weekly.filter((pl.col("team") == "KC") & (pl.col("week") == 1))
    kc_w1_ewm = decayed.filter((pl.col("team") == "KC") & (pl.col("week") == 1))
    assert kc_w1_ewm["epa_mean_ewm"][0] == pytest.approx(kc_w1_raw["epa_mean"][0])


def test_decay_forward_fills_byes():
    weekly = pl.DataFrame(
        {
            "team": ["AAA"] * 3,
            "season": [2023] * 3,
            "week": [1, 2, 4],
            "epa_mean": [1.0, 2.0, 4.0],
        }
    )
    schedule = pl.DataFrame({"season": [2023] * 4, "week": [1, 2, 3, 4]})
    decayed = add_windows(weekly, schedule, half_life=2.0)
    bye = decayed.filter(pl.col("week") == 3)
    wk2 = decayed.filter(pl.col("week") == 2)
    # bye carries week 2's ewm forward unchanged
    assert bye["epa_mean_ewm"][0] == pytest.approx(wk2["epa_mean_ewm"][0])


# ---- windows: L2 prior-season carryover ----


def test_carryover_blend_weights():
    # cur=2, prior=1, games=1, k=1 -> w=0.5 -> 0.5*1 + 0.5*2 = 1.5
    # null prior -> falls back to cur unchanged
    df = pl.DataFrame({"cur": [2.0, 2.0], "prior": [1.0, None], "games": [1, 1]})
    out = df.with_columns(
        carryover_blend(pl.col("cur"), pl.col("prior"), pl.col("games"), k=1.0).alias(
            "b"
        )
    )
    assert out["b"][0] == pytest.approx(1.5)
    assert out["b"][1] == pytest.approx(2.0)


def test_carryover_augments_and_no_prior_is_season_rate(
    weekly: pl.DataFrame, reg_schedule: pl.DataFrame
):
    out = add_windows(weekly, reg_schedule, carryover_k=2.0)
    assert "epa_mean_carry" in out.columns
    assert "epa_mean_season" in out.columns  # augments, does not replace
    # single-season fixture -> no prior -> carry == season-to-date mean rate
    kc = weekly.filter(pl.col("team") == "KC").sort("week")
    got = out.filter((pl.col("team") == "KC") & (pl.col("week") == 5))
    assert got["epa_mean_carry"][0] == pytest.approx(kc["epa_mean"].mean())


def test_carryover_blends_prior_season():
    # 2023 wk1: cur rate = 2.0 (1 game); prior 2022 final = 10.0; games=1, k=1
    # -> w = 1/(1+1) = 0.5 -> 0.5*10 + 0.5*2 = 6.0
    weekly = pl.DataFrame(
        {
            "team": ["AAA"] * 3,
            "season": [2022, 2023, 2023],
            "week": [1, 1, 2],
            "epa_mean": [10.0, 2.0, 4.0],
        }
    )
    schedule = pl.DataFrame({"season": [2022, 2023, 2023], "week": [1, 1, 2]})
    out = add_windows(weekly, schedule, carryover_k=1.0)
    row = out.filter((pl.col("season") == 2023) & (pl.col("week") == 1))
    assert row["epa_mean_carry"][0] == pytest.approx(6.0)


# ---- matrix ----


def test_matrix_meta_and_shape(matrix: pl.DataFrame, reg_schedule: pl.DataFrame):
    assert matrix.height == reg_schedule.height
    assert set(META_COLS) <= set(matrix.columns)
    # no stats exist before week 1, so week-1 games have null features
    week1 = matrix.filter(pl.col("week") == 1)
    assert week1["home_epa_season"].null_count() == week1.height


def test_matrix_uses_previous_week_stats(matrix: pl.DataFrame, windowed: pl.DataFrame):
    game = matrix.filter(pl.col("week") == 5).head(1)
    home = game["home_team"][0]
    expected = windowed.filter((pl.col("team") == home) & (pl.col("week") == 4))
    assert game["home_epa_season"][0] == pytest.approx(expected["epa_season"][0])
    assert game["home_epa_last_4w"][0] == pytest.approx(expected["epa_last_4w"][0])


def test_matrix_min_week(windowed: pl.DataFrame, reg_schedule: pl.DataFrame):
    trimmed = build_game_matrix(windowed, reg_schedule, min_week=4)
    assert trimmed["week"].min() >= 4
    assert trimmed.height < reg_schedule.height


# ---- anti-leakage ----


def test_future_weeks_do_not_leak(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    """Perturb week-5 plays; features for games through week 5 (built from
    weeks <= 4 via the 1-week lag) must be identical."""
    perturbed = pbp_sample.with_columns(
        pl.when(pl.col("week") == 5)
        .then(pl.col("epa") * 100 + 7)
        .otherwise(pl.col("epa"))
        .alias("epa"),
        pl.when(pl.col("week") == 5)
        .then(pl.col("yards_gained") + 50)
        .otherwise(pl.col("yards_gained"))
        .alias("yards_gained"),
    )

    # sanity: the perturbation changes week-5 weekly stats but not earlier weeks
    weekly_base = team_week_stats(play_features(pbp_sample))
    weekly_pert = team_week_stats(play_features(perturbed))
    assert not weekly_pert.filter(pl.col("week") == 5).equals(
        weekly_base.filter(pl.col("week") == 5)
    )
    assert_frame_equal(
        weekly_pert.filter(pl.col("week") < 5),
        weekly_base.filter(pl.col("week") < 5),
    )

    base = build_features(pbp_sample, schedule_sample)
    pert = build_features(perturbed, schedule_sample)
    assert_frame_equal(base.sort("game_id"), pert.sort("game_id"))

    # decay mode must be leak-safe too (same 1-week lag)
    base_d = build_features(pbp_sample, schedule_sample, half_life=3.0)
    pert_d = build_features(perturbed, schedule_sample, half_life=3.0)
    assert_frame_equal(base_d.sort("game_id"), pert_d.sort("game_id"))

    # epa-splits mode too
    base_e = build_features(pbp_sample, schedule_sample, epa_splits=True)
    pert_e = build_features(perturbed, schedule_sample, epa_splits=True)
    assert_frame_equal(base_e.sort("game_id"), pert_e.sort("game_id"))

    # carryover mode too
    base_c = build_features(pbp_sample, schedule_sample, carryover_k=2.0)
    pert_c = build_features(perturbed, schedule_sample, carryover_k=2.0)
    assert_frame_equal(base_c.sort("game_id"), pert_c.sort("game_id"))

    # opp_adjust mode too: week-w ratings only ever use weeks < w, so
    # perturbing week 5 must not change any row's opponent-adjusted cols
    base_o = build_features(pbp_sample, schedule_sample, opp_adjust=True)
    pert_o = build_features(perturbed, schedule_sample, opp_adjust=True)
    assert_frame_equal(base_o.sort("game_id"), pert_o.sort("game_id"))


# ---- L3 injuries ----


def _injuries(rows: list[tuple[str, int, str, str]]) -> pl.DataFrame:
    """(team, week, position, report_status) rows for 2023 REG."""
    return pl.DataFrame(
        {
            "season": [2023] * len(rows),
            "game_type": ["REG"] * len(rows),
            "team": [r[0] for r in rows],
            "week": [r[1] for r in rows],
            "position": [r[2] for r in rows],
            "report_status": [r[3] for r in rows],
        }
    )


def test_injuries_join_own_week_no_lag(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    # KC QB Out in week 2 only: the week-2 game carries it on KC's side
    # (own week, no lag); all other KC weeks and the opponent stay 0.
    inj = _injuries([("KC", 2, "QB", "Out")])
    base = build_features(pbp_sample, schedule_sample)
    out = build_features(pbp_sample, schedule_sample, injuries=inj)

    # only injury cols are added; the baseline matrix is untouched
    added = set(out.columns) - set(base.columns)
    assert added == {
        f"{side}_inj_{g}_{m}"
        for side in ("home", "away")
        for g in ("qb", "skill", "ol", "def")
        for m in ("out", "q", "burden")
    }

    kc = (pl.col("home_team") == "KC") | (pl.col("away_team") == "KC")
    wk2 = out.filter((pl.col("week") == 2) & kc)
    assert wk2.height == 1
    r = wk2.row(0, named=True)
    side = "home" if r["home_team"] == "KC" else "away"
    other = "away" if side == "home" else "home"
    assert r[f"{side}_inj_qb_out"] == 1
    assert r[f"{other}_inj_qb_out"] == 0  # opponent has no injuries -> 0-filled

    # no lag and no bleed: every other KC week shows qb_out == 0
    for r in out.filter((pl.col("week") != 2) & kc).iter_rows(named=True):
        side = "home" if r["home_team"] == "KC" else "away"
        assert r[f"{side}_inj_qb_out"] == 0


# ---- L3 schedule context ----


def test_schedule_context_cols_and_values(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    base = build_features(pbp_sample, schedule_sample)
    out = build_features(pbp_sample, schedule_sample, schedule_ctx=True)

    assert set(out.columns) - set(base.columns) == {
        "rest_diff",
        "home_off_bye",
        "away_off_bye",
        "home_short_week",
        "away_short_week",
        "thursday",
        "monday",
        "div_game",
    }
    assert out.height == base.height  # join on game_id drops nothing

    reg = schedule_sample.filter(pl.col("game_type") == "REG").select(
        "game_id", "home_rest", "away_rest"
    )
    chk = out.join(reg, on="game_id").with_columns(
        exp=pl.col("home_rest") - pl.col("away_rest")
    )
    assert (chk["rest_diff"] == chk["exp"]).all()


# ---- L4 opponent-adjusted ratings ----


def _team_game(
    posteam: str, defteam: str, week: int, epa: float, season: int = 2023
) -> tuple:
    return (season, week, posteam, defteam, epa)


def _synthetic_team_games(season: int = 2023) -> pl.DataFrame:
    """4-team league where A and B have identical raw offensive epa, but
    A's games came against a strong defense (D) and B's against a weak
    one (C) — so an opponent-adjusted rating should separate them even
    though the raw stat cannot. Extra rows (D vs A/C, C vs B) link the
    two schedule clusters together without touching A/B's own raw mean
    (computed only from A/B's *own* posteam rows)."""
    rows = [
        _team_game("A", "D", 1, 1.0, season),
        _team_game("A", "D", 2, 1.0, season),
        _team_game("B", "C", 1, 1.0, season),
        _team_game("B", "C", 2, 1.0, season),
        _team_game("D", "A", 1, 0.0, season),
        _team_game("C", "B", 1, 0.0, season),
        _team_game("C", "D", 1, -1.0, season),
        _team_game("D", "C", 1, 1.0, season),
    ]
    return pl.DataFrame(
        rows, schema=["season", "week", "posteam", "defteam", "epa"], orient="row"
    )


def test_opponent_ratings_adjust_for_strength_of_schedule():
    team_games = _synthetic_team_games()

    raw = team_games.group_by("posteam").agg(pl.col("epa").mean())
    raw_a = raw.filter(pl.col("posteam") == "A")["epa"][0]
    raw_b = raw.filter(pl.col("posteam") == "B")["epa"][0]
    assert raw_a == pytest.approx(raw_b)  # raw stat can't tell them apart

    fit = fit_opponent_ratings(
        team_games, "epa", lam=1.0, prior_weight=0.0, season=2023, week=5
    )
    off_a = fit.filter(pl.col("team") == "A")["off_rating"][0]
    off_b = fit.filter(pl.col("team") == "B")["off_rating"][0]
    assert off_a > off_b  # adjustment reveals A faced the tougher schedule


def test_opponent_ratings_shrink_toward_zero_with_large_lambda():
    team_games = _synthetic_team_games()
    loose = fit_opponent_ratings(
        team_games, "epa", lam=0.1, prior_weight=0.0, season=2023, week=5
    )
    tight = fit_opponent_ratings(
        team_games, "epa", lam=1e6, prior_weight=0.0, season=2023, week=5
    )
    loose_mag = loose["off_rating"].abs().sum()
    tight_mag = tight["off_rating"].abs().sum()
    assert tight_mag < loose_mag
    assert tight_mag == pytest.approx(0.0, abs=1e-3)


def test_opponent_ratings_prior_weight():
    prior_games = _synthetic_team_games(season=2022)

    # prior_weight=0 -> nothing to fit for week 1 of a fresh season (no
    # current-season rows exist yet, week <= week - 1 == 0)
    no_prior = fit_opponent_ratings(
        prior_games, "epa", lam=1.0, prior_weight=0.0, season=2023, week=1
    )
    assert no_prior.height == 0

    # prior_weight > 0 -> week-1 ratings are nonzero and reflect the prior
    # season's strength-of-schedule-adjusted gap between A and B
    with_prior = fit_opponent_ratings(
        prior_games, "epa", lam=1.0, prior_weight=0.5, season=2023, week=1
    )
    assert with_prior.height > 0
    off_a = with_prior.filter(pl.col("team") == "A")["off_rating"][0]
    off_b = with_prior.filter(pl.col("team") == "B")["off_rating"][0]
    assert off_a != pytest.approx(0.0)
    assert off_a > off_b


def test_opponent_ratings_prior_season_affects_week1_no_leak(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    """Mirrors the qb_ctx/carryover anti-leak style: mutating the *prior*
    season is allowed to change week-1 ratings (it's legitimate input),
    but week 1 stays null without any prior season loaded at all."""
    no_prior = build_features(pbp_sample, schedule_sample, opp_adjust=True)
    week1 = no_prior.filter(pl.col("week") == 1)
    assert week1["home_epa_adj_off"].null_count() == week1.height

    prior = pbp_sample.with_columns(
        pl.lit(2022).cast(pbp_sample.schema["season"]).alias("season")
    )
    combined = pl.concat([prior, pbp_sample], how="vertical_relaxed")
    base = build_features(combined, schedule_sample, opp_adjust=True)
    base_week1 = base.filter(pl.col("week") == 1)
    assert base_week1["home_epa_adj_off"].null_count() == 0  # prior warms week 1

    perturbed_prior = prior.with_columns((pl.col("epa") * 100 + 7).alias("epa"))
    combined_pert = pl.concat([perturbed_prior, pbp_sample], how="vertical_relaxed")
    pert = build_features(combined_pert, schedule_sample, opp_adjust=True)
    pert_week1 = pert.filter(pl.col("week") == 1)

    assert not base_week1.select("home_epa_adj_off", "away_epa_adj_off").equals(
        pert_week1.select("home_epa_adj_off", "away_epa_adj_off")
    )


def test_opp_adjust_toggle(pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame):
    base = build_features(pbp_sample, schedule_sample)
    out = build_features(pbp_sample, schedule_sample, opp_adjust=True)

    added = set(out.columns) - set(base.columns)
    expected = {
        f"{side}_{stat}_adj_{part}"
        for side in ("home", "away")
        for stat in STATS
        for part in ("off", "def")
    } | {"adj_rating_diff"}
    assert added == expected
    assert out.height == base.height  # join on (team, season, week) drops nothing


def test_team_games_frame_grain(plays: pl.DataFrame):
    tg = team_games_frame(plays)
    keys = tg.select("season", "week", "posteam", "defteam")
    assert keys.height == keys.unique().height
    assert set(STATS) <= set(tg.columns)


# ---- registry ----


def test_v1_team_feature_set(matrix: pl.DataFrame):
    feature_cols = get_feature_set("v1_team").columns(matrix)
    assert feature_cols
    assert set(feature_cols).isdisjoint(META_COLS)
    assert set(feature_cols) | set(META_COLS) == set(matrix.columns)


def test_unknown_feature_set_raises():
    with pytest.raises(KeyError, match="unknown feature set"):
        get_feature_set("nope")


@pytest.fixture(scope="module")
def adj_matrix(windowed: pl.DataFrame, reg_schedule: pl.DataFrame, plays: pl.DataFrame):
    matrix = build_game_matrix(windowed, reg_schedule)
    return add_opponent_ratings(
        matrix, team_games_frame(plays), lam=10.0, prior_weight=0.3
    )


def test_v2_adj_only_feature_set(adj_matrix: pl.DataFrame):
    feature_cols = get_feature_set("v2_adj_only").columns(adj_matrix)
    expected = {
        f"{side}_{stat}_adj_{part}"
        for side in ("home", "away")
        for stat in STATS
        for part in ("off", "def")
    } | {"adj_rating_diff"}
    assert set(feature_cols) == expected


def test_v2_adj_only_errors_without_opp_adjust(matrix: pl.DataFrame):
    with pytest.raises(ValueError, match="opp_adjust"):
        get_feature_set("v2_adj_only").columns(matrix)


def test_v2_adj_lean_feature_set(adj_matrix: pl.DataFrame):
    feature_cols = get_feature_set("v2_adj_lean").columns(adj_matrix)
    adj_cols = set(get_feature_set("v2_adj_only").columns(adj_matrix))
    assert adj_cols <= set(feature_cols)
    lean_only = set(feature_cols) - adj_cols
    assert lean_only  # picked up some rate-stat core cols too
    stems = [
        "epa_mean",
        "success_mean",
        "cpoe_mean",
        "pass_oe_mean",
        "sack_mean",
        "first_down_mean",
    ]
    for c in lean_only:
        assert any(stem in c for stem in stems)
        assert c.startswith(("home_", "away_"))
        assert c.endswith("_season") or "_last_" in c
