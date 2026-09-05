"""The guardrail bar and the replay policies (#58).

The point of the bar is that it rejects rules, so most of these check something
failing to qualify.
"""

from g_nfl.picks.backtest import replay_season, run
from g_nfl.picks.guardrails import build_rules, fit, flags, load_config

CONFIG = load_config()


def _row(season, week, picker, game_id, spread, home, won, slot="regular", gap=None):
    return {
        "picker": picker,
        "season": season,
        "week": week,
        "game_id": game_id,
        "slot": slot,
        "team": "AAA",
        "opp": "BBB",
        "picked_home": home,
        "line": spread,
        "picked_spread": spread,
        "picked_pool": spread,
        "picked_market": None if gap is None else spread - gap,
        "gap": gap,
        "gap_side": None
        if gap is None
        else ("worse" if gap < 0 else "better" if gap > 0 else "same"),
        "won": won,
    }


SEASONS = [2020, 2021, 2022, 2023, 2025]


def _sample(bad_seasons=5):
    """Road sides of a 7+ line, hitting 20% in `bad_seasons` and 50% elsewhere.

    Every game also carries a control pick on a 1-point line at 50%, so the
    field's base rate has something to sit on.
    """
    rows = []
    for i, season in enumerate(SEASONS):
        for g in range(30):
            won = (g % 5 == 0) if i < bad_seasons else (g % 2 == 0)
            rows.append(
                _row(season, g, "p1", f"{season}_01_AAA_B{g:02d}", 9.0, False, won=won)
            )
            rows.append(
                _row(
                    season,
                    g,
                    "p1",
                    f"{season}_01_CCC_D{g:02d}",
                    1.0,
                    False,
                    won=g % 2 == 0,
                )
            )
    return rows


def test_a_stable_bad_cell_qualifies():
    (road,) = [f for f in fit(_sample(), CONFIG) if f.rule.id == "road_7_plus"]
    assert road.qualifies, road.reason
    assert road.shrunk_pct < road.base


def test_a_thin_cell_never_qualifies():
    rows = [
        _row(2021, w, "p1", f"2021_01_AAA_B{w:02d}", 9.0, False, won=False)
        for w in range(5)
    ]
    (road,) = [f for f in fit(rows, CONFIG) if f.rule.id == "road_7_plus"]
    assert not road.qualifies
    assert "games" in road.reason


def test_a_cell_that_is_only_bad_in_some_seasons_does_not_qualify():
    (road,) = [
        f for f in fit(_sample(bad_seasons=2), CONFIG) if f.rule.id == "road_7_plus"
    ]
    assert not road.qualifies
    assert "seasons" in road.reason


def test_flags_only_fire_for_qualifying_rules():
    fits = fit(_sample(), CONFIG)
    side = _row(2026, 1, "Griffin", "2026_01_AAA_BBB", 9.0, False, won=False)
    fired = flags(side, fits)
    assert [f.rule.id for f in fired] == ["road_7_plus"]

    clean = _row(2026, 1, "Griffin", "2026_01_AAA_BBB", 1.0, False, won=False)
    assert flags(clean, fits) == []


def test_flip_takes_the_other_side_of_the_same_game():
    fits = fit(_sample(), CONFIG)
    entry = [
        _row(
            2025,
            1,
            "Reichert",
            "2025_01_AAA_B99",
            9.0,
            False,
            won=False,
            slot="best_bet",
        )
    ]
    out = replay_season(entry, fits, "flip", {"Reichert"})
    assert out.actual == 0.0
    assert out.adjusted == 2.0  # a losing best bet flips to a winning one
    assert out.vetoed == 1


def test_an_unflagged_entry_is_left_alone():
    fits = fit(_sample(), CONFIG)
    entry = [_row(2025, 1, "Reichert", "2025_01_AAA_B99", 1.0, False, won=True)]
    out = replay_season(entry, fits, "flip", {"Reichert"})
    assert out.actual == out.adjusted == 1.0
    assert out.vetoed == 0


def test_walk_forward_never_fits_on_the_season_it_scores():
    rows = _sample() + [
        _row(2025, 1, "Reichert", "2025_01_AAA_B99", 9.0, False, won=False)
    ]
    seasons = [r.season for r in run(rows, {"Reichert"}, scheme="walk_forward")]
    assert 2020 not in seasons  # nothing earlier to train on


def test_advisory_rules_are_kept_out_of_the_replay():
    """`pool_worse_than_market` reads the close, unknowable at pick time."""
    rules = build_rules(CONFIG)
    advisory = [r.id for r in rules if r.advisory]
    assert advisory == ["pool_worse_than_market"]


def test_a_rule_the_bar_turned_down_can_still_be_replayed():
    """A candidate rule is measured before it has earned the board (item 5)."""
    fits = fit(_sample(bad_seasons=2), CONFIG)
    (road,) = [f for f in fits if f.rule.id == "road_7_plus"]
    assert not road.qualifies
    entry = [
        _row(
            2025,
            1,
            "Reichert",
            "2025_01_AAA_B99",
            9.0,
            False,
            won=False,
            slot="best_bet",
        )
    ]
    assert replay_season(entry, fits, "flip", {"Reichert"}).vetoed == 0
    forced = replay_season(entry, fits, "flip", {"Reichert"}, require_qualified=False)
    assert forced.vetoed == 1
    assert forced.adjusted == 2.0
