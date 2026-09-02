"""Hand-transcribed offensive_playcaller rows for data/coaches/playcallers.csv,
sourced from the annual "who calls plays for every NFL team" roundups (ESPN
2017/2023/2024/2025, Yardbarker 2020/2021/2022) — the one source type that
names the playcaller directly rather than just the OC/DC titleholder. No
equivalent full-league roundup was found for 2015, 2016, 2018, or 2019; those
seasons fall through to the OC/HC default in coaches.py's fill-remaining pass.

Re-running this module is safe: it only adds rows for (season, team) pairs
that don't already have an offensive_playcaller row.
"""

import polars as pl

from g_nfl.scraping.coaches import PLAYCALLER_COLUMNS

FULL_NAME_TO_ABBR = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Los Angeles Rams": "LA",
    "Los Angeles Chargers": "LAC",
    "Las Vegas Raiders": "LV",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "Seattle Seahawks": "SEA",
    "San Francisco 49ers": "SF",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington": "WAS",
    "Washington Commanders": "WAS",
}

# season -> (source_url, end_week, {full_team_name: (name, role_label)})
SEASONS = {
    2020: (
        "https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_callers_from_every_nfl_team/s1__32555903",
        17,
        {
            "Arizona Cardinals": "Kliff Kingsbury",
            "Atlanta Falcons": "Dirk Koetter",
            "Baltimore Ravens": "Greg Roman",
            "Buffalo Bills": "Brian Daboll",
            "Carolina Panthers": "Joe Brady",
            "Chicago Bears": "Matt Nagy",
            "Cincinnati Bengals": "Zac Taylor",
            "Cleveland Browns": "Kevin Stefanski",
            "Dallas Cowboys": "Kellen Moore",
            "Denver Broncos": "Pat Shurmur",
            "Detroit Lions": "Darrell Bevell",
            "Green Bay Packers": "Matt LaFleur",
            "Houston Texans": "Tim Kelly",
            "Indianapolis Colts": "Frank Reich",
            "Jacksonville Jaguars": "Jay Gruden",
            "Kansas City Chiefs": "Andy Reid",
            "Las Vegas Raiders": "Jon Gruden",
            "Los Angeles Chargers": "Shane Steichen",
            "Los Angeles Rams": "Sean McVay",
            "Miami Dolphins": "Chan Gailey",
            "Minnesota Vikings": "Gary Kubiak",
            "New England Patriots": "Josh McDaniels",
            "New Orleans Saints": "Sean Payton",
            "New York Giants": "Jason Garrett",
            "New York Jets": "Adam Gase",
            "Philadelphia Eagles": "Doug Pederson",
            "Pittsburgh Steelers": "Randy Fichtner",
            "San Francisco 49ers": "Kyle Shanahan",
            "Seattle Seahawks": "Brian Schottenheimer",
            "Tampa Bay Buccaneers": "Byron Leftwich",
            "Tennessee Titans": "Arthur Smith",
            "Washington": "Scott Turner",
        },
    ),
    2021: (
        "https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__35857394",
        18,
        {
            "Kansas City Chiefs": "Andy Reid",
            "New Orleans Saints": "Sean Payton",
            "Los Angeles Rams": "Sean McVay",
            "San Francisco 49ers": "Kyle Shanahan",
            "Green Bay Packers": "Matt LaFleur",
            "New England Patriots": "Josh McDaniels",
            "Indianapolis Colts": "Frank Reich",
            "Cleveland Browns": "Kevin Stefanski",
            "Las Vegas Raiders": "Jon Gruden",
            "Atlanta Falcons": "Arthur Smith",
            "Tampa Bay Buccaneers": "Byron Leftwich",
            "Baltimore Ravens": "Greg Roman",
            "Chicago Bears": "Matt Nagy",
            "Jacksonville Jaguars": "Darrell Bevell",
            "Dallas Cowboys": "Kellen Moore",
            "Arizona Cardinals": "Kliff Kingsbury",
            "Buffalo Bills": "Brian Daboll",
            "New York Giants": "Jason Garrett",
            "Carolina Panthers": "Joe Brady",
            "Washington Commanders": "Scott Turner",
            "Los Angeles Chargers": "Joe Lombardi",
            "Denver Broncos": "Pat Shurmur",
            "Cincinnati Bengals": "Zac Taylor",
            "Philadelphia Eagles": "Nick Sirianni",
            "Detroit Lions": "Anthony Lynn",
            "Tennessee Titans": "Todd Downing",
            "Houston Texans": "Tim Kelly",
            "Pittsburgh Steelers": "Matt Canada",
            "Minnesota Vikings": "Klint Kubiak",
            "New York Jets": "Mike LaFleur",
            "Seattle Seahawks": "Shane Waldron",
            # Miami: co-OC, handled separately below
        },
    ),
    2022: (
        "https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__37978942",
        18,
        {
            "Kansas City Chiefs": "Andy Reid",
            "Los Angeles Rams": "Sean McVay",
            "San Francisco 49ers": "Kyle Shanahan",
            "Green Bay Packers": "Matt LaFleur",
            "Jacksonville Jaguars": "Doug Pederson",
            "Tampa Bay Buccaneers": "Byron Leftwich",
            "Philadelphia Eagles": "Nick Sirianni",
            "Miami Dolphins": "Mike McDaniel",
            "Las Vegas Raiders": "Josh McDaniels",
            "Indianapolis Colts": "Frank Reich",
            "Dallas Cowboys": "Kellen Moore",
            "Cincinnati Bengals": "Zac Taylor",
            "Cleveland Browns": "Kevin Stefanski",
            "Baltimore Ravens": "Greg Roman",
            "New Orleans Saints": "Pete Carmichael",
            "Arizona Cardinals": "Kliff Kingsbury",
            "Washington Commanders": "Scott Turner",
            "Los Angeles Chargers": "Joe Lombardi",
            "Atlanta Falcons": "Arthur Smith",
            "Buffalo Bills": "Ken Dorsey",
            "Seattle Seahawks": "Shane Waldron",
            "Minnesota Vikings": "Kevin O'Connell",
            "Detroit Lions": "Ben Johnson",
            "New York Giants": "Mike Kafka",
            "New York Jets": "Mike LaFleur",
            "Pittsburgh Steelers": "Matt Canada",
            "Houston Texans": "Pep Hamilton",
            "Tennessee Titans": "Todd Downing",
            "Carolina Panthers": "Ben McAdoo",
            "Denver Broncos": "Nathaniel Hackett",
            "Chicago Bears": "Luke Getsy",
            # New England: Patricia/Judge experiment, handled separately
        },
    ),
    2023: (
        "https://www.espn.com/nfl/story/_/id/38108724/key-intel-all-32-nfl-playcallers-including-mike-mccarthy",
        18,
        {
            "Buffalo Bills": "Ken Dorsey",
            "Miami Dolphins": "Mike McDaniel",
            "New England Patriots": "Bill O'Brien",
            "New York Jets": "Nathaniel Hackett",
            "Baltimore Ravens": "Todd Monken",
            "Cincinnati Bengals": "Zac Taylor",
            "Cleveland Browns": "Kevin Stefanski",
            "Pittsburgh Steelers": "Matt Canada",
            "Houston Texans": "Bobby Slowik",
            "Indianapolis Colts": "Shane Steichen",
            "Jacksonville Jaguars": "Doug Pederson",
            "Tennessee Titans": "Tim Kelly",
            "Denver Broncos": "Sean Payton",
            "Kansas City Chiefs": "Andy Reid",
            "Las Vegas Raiders": "Josh McDaniels",
            "Los Angeles Chargers": "Kellen Moore",
            "Dallas Cowboys": "Mike McCarthy",
            "New York Giants": "Mike Kafka",
            "Philadelphia Eagles": "Brian Johnson",
            "Washington Commanders": "Eric Bieniemy",
            "Chicago Bears": "Luke Getsy",
            "Detroit Lions": "Ben Johnson",
            "Green Bay Packers": "Matt LaFleur",
            "Minnesota Vikings": "Kevin O'Connell",
            "Atlanta Falcons": "Arthur Smith",
            "Carolina Panthers": "Frank Reich",
            "New Orleans Saints": "Pete Carmichael",
            "Tampa Bay Buccaneers": "Dave Canales",
            "Arizona Cardinals": "Drew Petzing",
            "Los Angeles Rams": "Sean McVay",
            "San Francisco 49ers": "Kyle Shanahan",
            "Seattle Seahawks": "Shane Waldron",
        },
    ),
    2024: (
        "https://www.espn.com/espn/print?id=41018846",
        18,
        {
            "Buffalo Bills": "Joe Brady",
            "Miami Dolphins": "Mike McDaniel",
            "New England Patriots": "Alex Van Pelt",
            "New York Jets": "Nathaniel Hackett",
            "Baltimore Ravens": "Todd Monken",
            "Cincinnati Bengals": "Zac Taylor",
            "Cleveland Browns": "Kevin Stefanski",
            "Pittsburgh Steelers": "Arthur Smith",
            "Houston Texans": "Bobby Slowik",
            "Indianapolis Colts": "Shane Steichen",
            "Jacksonville Jaguars": "Press Taylor",
            "Tennessee Titans": "Brian Callahan",
            "Denver Broncos": "Sean Payton",
            "Kansas City Chiefs": "Andy Reid",
            "Las Vegas Raiders": "Luke Getsy",
            "Los Angeles Chargers": "Greg Roman",
            "Dallas Cowboys": "Mike McCarthy",
            "New York Giants": "Brian Daboll",
            "Philadelphia Eagles": "Kellen Moore",
            "Washington Commanders": "Kliff Kingsbury",
            "Chicago Bears": "Shane Waldron",
            "Detroit Lions": "Ben Johnson",
            "Green Bay Packers": "Matt LaFleur",
            "Minnesota Vikings": "Kevin O'Connell",
            "Atlanta Falcons": "Zac Robinson",
            "Carolina Panthers": "Dave Canales",
            "New Orleans Saints": "Klint Kubiak",
            "Tampa Bay Buccaneers": "Liam Coen",
            "Arizona Cardinals": "Drew Petzing",
            "Los Angeles Rams": "Sean McVay",
            "San Francisco 49ers": "Kyle Shanahan",
            "Seattle Seahawks": "Ryan Grubb",
        },
    ),
    2025: (
        "https://www.espn.com/nfl/story/_/id/46137832/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-brian-schottenheimer",
        18,
        {
            "Arizona Cardinals": "Drew Petzing",
            "Atlanta Falcons": "Zac Robinson",
            "Baltimore Ravens": "Todd Monken",
            "Buffalo Bills": "Joe Brady",
            "Carolina Panthers": "Dave Canales",
            "Chicago Bears": "Ben Johnson",
            "Cincinnati Bengals": "Zac Taylor",
            "Cleveland Browns": "Kevin Stefanski",
            "Dallas Cowboys": "Brian Schottenheimer",
            "Denver Broncos": "Sean Payton",
            "Detroit Lions": "John Morton",
            "Green Bay Packers": "Matt LaFleur",
            "Houston Texans": "Nick Caley",
            "Indianapolis Colts": "Shane Steichen",
            "Jacksonville Jaguars": "Liam Coen",
            "Kansas City Chiefs": "Andy Reid",
            "Los Angeles Chargers": "Greg Roman",
            "Los Angeles Rams": "Sean McVay",
            "Las Vegas Raiders": "Chip Kelly",
            "Miami Dolphins": "Mike McDaniel",
            "Minnesota Vikings": "Kevin O'Connell",
            "New England Patriots": "Josh McDaniels",
            "New Orleans Saints": "Kellen Moore",
            "New York Giants": "Mike Kafka",
            "New York Jets": "Tanner Engstrand",
            "Philadelphia Eagles": "Kevin Patullo",
            "Pittsburgh Steelers": "Arthur Smith",
            "San Francisco 49ers": "Kyle Shanahan",
            "Seattle Seahawks": "Klint Kubiak",
            "Tampa Bay Buccaneers": "Josh Grizzard",
            "Tennessee Titans": "Brian Callahan",
            "Washington Commanders": "Kliff Kingsbury",
        },
    ),
}


def _build_rows_from_sources() -> list[tuple]:
    rows = []
    for season, (url, end_week, teams) in SEASONS.items():
        for full_name, name in teams.items():
            team = FULL_NAME_TO_ABBR[full_name]
            rows.append(
                (
                    season,
                    team,
                    "offensive_playcaller",
                    name,
                    1,
                    end_week,
                    0,
                    None,
                    None,
                    None,
                    url,
                    "medium",
                )
            )
    return rows


def build_rows() -> list[tuple]:
    rows = _build_rows_from_sources()
    # co-playcaller / disputed situations handled with notes instead of a single name
    rows.append(
        (
            2021,
            "MIA",
            "offensive_playcaller",
            None,
            1,
            18,
            0,
            None,
            None,
            None,
            "https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__35857394: co-OC George Godsey/Eric Studesville, no single playcaller named",
            "low",
        )
    )
    rows.append(
        (
            2022,
            "NE",
            "offensive_playcaller",
            None,
            1,
            18,
            0,
            None,
            None,
            None,
            "https://www.yardbarker.com/nfl/articles/who_are_the_new_play_callers_for_the_2022_nfl_season/s1__37627769: Matt Patricia/Joe Judge shared-committee experiment, no single playcaller named",
            "low",
        )
    )
    return rows


def merge_into_csv(
    rows: list[tuple], path: str = "data/coaches/playcallers.csv"
) -> pl.DataFrame:
    """Add offensive_playcaller rows for any (season, team) that doesn't already have one."""
    sweep = pl.DataFrame(rows, schema=PLAYCALLER_COLUMNS, orient="row")
    existing = pl.read_csv(path)
    existing_op_keys = (
        existing.filter(pl.col("role") == "offensive_playcaller")
        .select(["season", "team"])
        .unique()
    )
    sweep_new = sweep.join(existing_op_keys, on=["season", "team"], how="anti")
    out = pl.concat([existing, sweep_new], how="diagonal_relaxed").sort(
        ["season", "team", "role", "start_week"]
    )
    out.write_csv(path)
    print(
        f"existing={len(existing)} sweep_total={len(sweep)} sweep_added={len(sweep_new)} "
        f"skipped_dup={len(sweep) - len(sweep_new)} final={len(out)}"
    )
    return out


def fill_defaults(path: str = "data/coaches/playcallers.csv") -> pl.DataFrame:
    """Per spec rule 3: for any (season, team) still missing a playcaller row,
    default offensive_playcaller to the OC and defensive_playcaller to the DC
    (both confidence=low). Where no OC/DC title was found at all, default to
    the HC instead — a confirmed pattern (SF/Shanahan, ARI/Kingsbury, and
    similar) rather than a guess, but still unverified for that specific
    team-season, so still confidence=low.
    """
    df = pl.read_csv(path)
    all_ts = df.select(["season", "team"]).unique()
    hc_week1 = (
        df.filter((pl.col("role") == "HC") & (pl.col("start_week") == 1))
        .select(["season", "team", "name", "end_week"])
        .rename({"name": "hc_name", "end_week": "hc_end_week"})
    )

    for target_role, title_role, title_col in [
        ("offensive_playcaller", "OC", "oc_name"),
        ("defensive_playcaller", "DC", "dc_name"),
    ]:
        have = (
            df.filter(pl.col("role") == target_role).select(["season", "team"]).unique()
        )
        need = all_ts.join(have, on=["season", "team"], how="anti")
        title = (
            df.filter(pl.col("role") == title_role)
            .select(["season", "team", "name", "end_week"])
            .rename({"name": title_col})
        )
        need = need.join(title, on=["season", "team"], how="left").join(
            hc_week1, on=["season", "team"], how="left"
        )

        rows = []
        for r in need.iter_rows(named=True):
            if r[title_col] is not None:
                name, note, ew = (
                    r[title_col],
                    f"default: {title_role} per spec rule 3, no playcaller-specific source found",
                    r["end_week"],
                )
            elif r["hc_name"] is not None:
                name, note, ew = (
                    r["hc_name"],
                    f"default: no {title_role} title found (wiki sweep) — HC assumed, unverified",
                    r["hc_end_week"],
                )
            else:
                continue
            rows.append(
                (
                    r["season"],
                    r["team"],
                    target_role,
                    name,
                    1,
                    int(ew) if ew else 18,
                    0,
                    None,
                    None,
                    None,
                    note,
                    "low",
                )
            )

        if rows:
            sweep = pl.DataFrame(rows, schema=PLAYCALLER_COLUMNS, orient="row")
            df = pl.concat([df, sweep], how="diagonal_relaxed")

    df = df.sort(["season", "team", "role", "start_week"])
    df.write_csv(path)
    return df


def repair_hc_playcaller_continuity(
    path: str = "data/coaches/playcallers.csv",
) -> pl.DataFrame:
    """Fix a systematic bug in fill_defaults(): defaulting offensive_playcaller to
    the OC is wrong for a head coach who is a known career self-caller (Reid,
    Payton, LaFleur, ...) in any season the sourced roundups (playcaller_sources.py)
    didn't cover. That default silently breaks the person-identity chain the
    tempo/pace feature depends on (r=+0.41 through a coach's own team change,
    per notes/playcaller-network.md) — e.g. KC reads
    Reid -> Bieniemy -> Bieniemy -> Reid across 2017-2020 in the raw defaults,
    when Reid called plays the entire time.

    Only touches rows this session's fill_defaults() wrote (confidence='low',
    source_url starting with 'default: OC') — never a sourced medium/high row.

    Rule, same-team evidence preferred, cross-team as fallback, skip if a coach
    has evidence on both sides (both self-calling and delegating somewhere in
    the sourced rows) so the fix cannot walk over a real change in behavior:
    1. If this HC self-called (playcaller == HC) in a *sourced* (medium/high)
       row for the *same team*, and never delegated for that team in a sourced
       row, repair to the HC.
    2. Else if this HC self-called in a sourced row for *any* team, and never
       delegated in *any* sourced row, repair to the HC.
    3. Otherwise leave the row alone — no repair, stays a low-confidence OC
       default, per the same "don't guess" rule the original spec used.
    """
    df = pl.read_csv(path)
    op = df.filter(pl.col("role") == "offensive_playcaller")
    hc = (
        df.filter((pl.col("role") == "HC") & (pl.col("start_week") == 1))
        .select(["season", "team", "name"])
        .rename({"name": "hc_name"})
    )
    op_hc = op.join(hc, on=["season", "team"], how="left")

    sourced = op_hc.filter(pl.col("confidence").is_in(["medium", "high"]))
    self_calls = sourced.filter(pl.col("name") == pl.col("hc_name"))
    delegations = sourced.filter(pl.col("name") != pl.col("hc_name"))

    same_team_self_callers = set(
        self_calls.select(["team", "hc_name"]).unique().iter_rows()
    )
    same_team_delegators = set(
        delegations.select(["team", "hc_name"]).unique().iter_rows()
    )
    any_team_self_callers = set(self_calls["hc_name"].unique())
    any_team_delegators = set(delegations["hc_name"].unique())

    to_fix = op_hc.filter(
        (pl.col("confidence") == "low")
        & pl.col("source_url").str.starts_with("default: OC")
    )

    fixed_ids = []
    for r in to_fix.iter_rows(named=True):
        team, hc_name = r["team"], r["hc_name"]
        if hc_name is None:
            continue
        if (team, hc_name) in same_team_self_callers and (
            team,
            hc_name,
        ) not in same_team_delegators:
            fixed_ids.append(
                (
                    r["season"],
                    r["team"],
                    r["start_week"],
                    hc_name,
                    "same-team continuity",
                )
            )
        elif hc_name in any_team_self_callers and hc_name not in any_team_delegators:
            fixed_ids.append(
                (
                    r["season"],
                    r["team"],
                    r["start_week"],
                    hc_name,
                    "cross-team identity",
                )
            )

    fix_df = (
        pl.DataFrame(
            fixed_ids,
            schema=["season", "team", "start_week", "new_name", "rule"],
            orient="row",
        )
        if fixed_ids
        else pl.DataFrame(
            schema={
                "season": pl.Int64,
                "team": pl.Utf8,
                "start_week": pl.Int64,
                "new_name": pl.Utf8,
                "rule": pl.Utf8,
            }
        )
    )

    df = df.join(fix_df, on=["season", "team", "start_week"], how="left")
    is_fixed = (pl.col("role") == "offensive_playcaller") & pl.col(
        "new_name"
    ).is_not_null()
    df = df.with_columns(
        pl.when(is_fixed)
        .then(pl.col("new_name"))
        .otherwise(pl.col("name"))
        .alias("name"),
        pl.when(is_fixed)
        .then(
            pl.lit("inferred: adjacent/cross-season HC-playcaller continuity (")
            + pl.col("rule")
            + pl.lit(")")
        )
        .otherwise(pl.col("source_url"))
        .alias("source_url"),
    ).drop(["new_name", "rule"])

    df = df.sort(["season", "team", "role", "start_week"])
    df.write_csv(path)

    print(
        f"repaired {len(fix_df)} offensive_playcaller rows via HC continuity "
        f"({(fix_df['rule'] == 'same-team continuity').sum() if len(fix_df) else 0} same-team, "
        f"{(fix_df['rule'] == 'cross-team identity').sum() if len(fix_df) else 0} cross-team)"
    )
    return df


if __name__ == "__main__":
    merge_into_csv(build_rows())
    fill_defaults()
    repair_hc_playcaller_continuity()
