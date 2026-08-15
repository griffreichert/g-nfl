"""Role/luck decomposition and the percentiles it produces (issue #86). Network-free."""

import polars as pl

from g_nfl.fantasy.outcomes import (
    MIN_GAMES,
    adp_baseline,
    bucket_distributions,
    no_show_rate,
    outcome_percentiles,
    played,
    residuals,
)


def _history(n_per_rank: int = 8) -> pl.DataFrame:
    """A market that is right on average: ppg falls smoothly with ADP rank.

    Rookies get a wide role spread around that curve, prime players a narrow
    one. Luck is symmetric noise on top, identical for both, so any difference
    the buckets show has to come from the role component.
    """
    rows = []
    for rank in range(1, 21):
        market_ppg = 20.0 - 0.5 * rank
        for i in range(n_per_rank):
            spread = 0.6 if i % 2 else 0.05  # rookies wide, prime tight
            swing = (i - n_per_rank / 2) / (n_per_rank / 2)
            rows.append(
                {
                    "gsis_id": f"p{rank}-{i}",
                    "season": 2020 + (i % 4),
                    "position": "RB",
                    "experience": "rookie" if i % 2 else "prime",
                    "adp_tier": "early",
                    "adp": float(rank),
                    "pos_adp_rank": rank,
                    "games": 17,
                    "xfp_ppg": market_ppg * (1 + spread * swing),
                    "actual_ppg": market_ppg * (1 + spread * swing) + swing,
                }
            )
    return pl.DataFrame(rows)


def test_baseline_tracks_the_market_curve():
    """The fitted baseline should land on the ppg the ADP rank implies."""
    curve = adp_baseline(_history())
    at_rank_10 = curve.filter(pl.col("pos_adp_rank") == 10)["baseline_ppg"][0]
    assert abs(at_rank_10 - 15.0) < 1.0


def test_role_spread_separates_rookies_from_prime():
    """The whole premise: role variance differs by bucket, luck does not."""
    buckets = bucket_distributions(residuals(_history()))
    by_experience = {r["experience"]: r for r in buckets.iter_rows(named=True)}

    rookie_width = (
        by_experience["rookie"]["role_p90"] - by_experience["rookie"]["role_p10"]
    )
    prime_width = (
        by_experience["prime"]["role_p90"] - by_experience["prime"]["role_p10"]
    )
    assert rookie_width > 4 * prime_width

    # Luck was drawn the same way for both, so it should not separate them.
    luck_ratio = by_experience["rookie"]["luck_sd"] / by_experience["prime"]["luck_sd"]
    assert 0.8 < luck_ratio < 1.25


def test_short_seasons_leave_the_pool_and_land_in_the_no_show_rate():
    history = _history().with_columns(
        pl.when(pl.col("gsis_id") == "p1-0")
        .then(MIN_GAMES - 1)
        .otherwise(pl.col("games"))
        .alias("games")
    )
    assert played(history).height == history.height - 1

    rate = no_show_rate(history).filter(pl.col("experience") == "prime")
    assert rate["no_show_rate"][0] > 0
    assert (
        no_show_rate(history).filter(pl.col("experience") == "rookie")["no_show_rate"][
            0
        ]
        == 0
    )


def test_percentiles_widen_for_the_wider_bucket():
    resid = residuals(_history())
    board = pl.DataFrame(
        {
            "gsis_id": ["new", "old"],
            "position": ["RB", "RB"],
            "proj_ppg": [15.0, 15.0],
            "experience": ["rookie", "prime"],
            "adp_tier": ["early", "early"],
        }
    )
    out = outcome_percentiles(board, resid, draws=2000)
    ranges = {
        r["gsis_id"]: r["ceiling"] - r["floor"] for r in out.iter_rows(named=True)
    }

    # Same central projection, different range: the point of the whole ticket.
    assert ranges["new"] > ranges["old"]
    assert out["floor"].to_list() < out["ceiling"].to_list()
