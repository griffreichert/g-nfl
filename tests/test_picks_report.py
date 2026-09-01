"""The case artifact (#58).

It exists so the argument shown to the room is generated rather than retyped,
so the tests check it is assembled from the live functions and that the caveat
cannot be dropped.
"""

from unittest.mock import patch

from g_nfl.picks import report


class _Standing:
    def __init__(self, entry, points, available, share, weeks):
        self.entry, self.points = entry, points
        self.available, self.share, self.weeks = available, share, weeks


class _Ledger:
    def __init__(self, standings):
        self.standings = standings


ROWS = [
    {
        "picker": "Griffin",
        "season": 2025,
        "week": 1,
        "game_id": "2025_01_AAA_BBB",
        "slot": "regular",
        "team": "AAA",
        "picked_home": False,
        "picked_spread": 9.0,
        "gap": None,
        "gap_side": None,
        "won": False,
    }
]


def _build(season=2025, standings=()):
    with (
        patch.object(report, "load_history", return_value=ROWS),
        patch("g_nfl.api.main.get_ledger", return_value=_Ledger(list(standings))),
    ):
        return report.build(season)


def test_the_case_carries_every_section():
    text = _build()
    for heading in ("What we are bad at", "What avoiding them", "This season"):
        assert heading in text


def test_the_caveat_is_always_there():
    """Structure leakage is the one thing anyone shown this has to be told."""
    assert "first honest out-of-sample season is 2026" in _build()


def test_a_season_with_nothing_graded_says_so():
    assert "Nothing graded yet for 2026" in _build(2026)


def test_the_ledger_table_comes_from_the_endpoint():
    text = _build(2025, [_Standing("TEAM", 37.5, 95, 0.395, 12)])
    assert "| TEAM | 37.5 | 95 | 39.5% | 12 |" in text


def test_rules_are_named_by_their_own_labels_rather_than_retyped():
    """The whole point: no number or name in here is written by hand."""
    from g_nfl.picks.guardrails import build_rules, load_config

    text = _build()
    for rule in build_rules(load_config()):
        assert rule.label in text
