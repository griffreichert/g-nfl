import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import nfl_data_py as nfl
import numpy as np
import pandas as pd

from g_nfl.utils.config import (
    CUR_SEASON,
    DEFAULT_WIN_PROB,
    EXPLOSIVE_PASS_THRESHOLD,
    EXPLOSIVE_RUN_THRESHOLD,
)

warnings.filterwarnings("ignore")


class PBPRBFantasyProjector:
    """
    RB Fantasy Projector built entirely on play-by-play data.
    Provides much more granular filtering and analysis capabilities.
    """

    def __init__(self, current_season=CUR_SEASON):
        self.current_season = current_season
        self.pbp_data = None
        self.rb_plays = None
        self.rb_stats = None
        self.team_stats = None
        self.schedules = None
        self.defensive_stats = None

    def load_data(
        self, weeks_filter: Optional[List[int]] = None, min_wp: float = DEFAULT_WIN_PROB
    ):
        """Load play-by-play data and extract RB-specific information"""
        print("Loading play-by-play data...")
        self.pbp_data = nfl.import_pbp_data([self.current_season])

        if weeks_filter:
            self.pbp_data = self.pbp_data[self.pbp_data["week"].isin(weeks_filter)]
            print(f"Filtered to weeks: {weeks_filter}")

        print("Loading schedules...")
        self.schedules = nfl.import_schedules([self.current_season])

        print("Processing RB plays...")
        self._process_rb_plays(min_wp)

        print("Calculating team metrics...")
        self.team_stats = self._calculate_team_metrics()

        print("Calculating defensive metrics...")
        self.defensive_stats = self._calculate_defensive_metrics()

        print("Building player stats from PBP data...")
        self._build_rb_stats()

        print("Data loading complete!")

    def _process_rb_plays(self, min_wp: float = DEFAULT_WIN_PROB):
        """Extract and filter RB-specific plays from PBP data"""
        # Filter to valid plays with win probability bounds (removes garbage time)
        valid_plays = self.pbp_data[
            (self.pbp_data["play_type"].isin(["run", "pass"]))
            & (self.pbp_data["wp"].between(min_wp, 1 - min_wp))
            & (~self.pbp_data["posteam"].isna())
            & (~self.pbp_data["defteam"].isna())
        ].copy()

        # Extract RB rushing plays
        rb_rushing = valid_plays[
            (valid_plays["play_type"] == "run") & (~valid_plays["rusher_id"].isna())
        ].copy()

        # Extract RB receiving plays (will need to filter by position later)
        rb_receiving = valid_plays[
            (valid_plays["play_type"] == "pass") & (~valid_plays["receiver_id"].isna())
        ].copy()

        # Store all play types
        self.rb_plays = {
            "rushing": rb_rushing,
            "receiving": rb_receiving,
            "all_valid": valid_plays,
        }

    def _calculate_team_metrics(self):
        """Calculate advanced team-level metrics from PBP data"""
        team_metrics = []

        for team in self.rb_plays["all_valid"]["posteam"].unique():
            team_plays = self.rb_plays["all_valid"][
                self.rb_plays["all_valid"]["posteam"] == team
            ]

            total_plays = len(team_plays)
            if total_plays == 0:
                continue

            # Basic rates
            rush_plays = team_plays[team_plays["play_type"] == "run"]
            rush_rate = len(rush_plays) / total_plays

            # Situational rates
            rz_plays = team_plays[team_plays["yardline_100"] <= 20]
            rz_rush_rate = (
                len(rz_plays[rz_plays["play_type"] == "run"]) / len(rz_plays)
                if len(rz_plays) > 0
                else 0
            )

            goal_line_plays = team_plays[team_plays["yardline_100"] <= 5]
            gl_rush_rate = (
                len(goal_line_plays[goal_line_plays["play_type"] == "run"])
                / len(goal_line_plays)
                if len(goal_line_plays) > 0
                else 0
            )

            # Game script analysis
            leading_plays = team_plays[team_plays["score_differential"] > 0]
            leading_rush_rate = (
                len(leading_plays[leading_plays["play_type"] == "run"])
                / len(leading_plays)
                if len(leading_plays) > 0
                else 0
            )

            trailing_plays = team_plays[team_plays["score_differential"] < 0]
            trailing_rush_rate = (
                len(trailing_plays[trailing_plays["play_type"] == "run"])
                / len(trailing_plays)
                if len(trailing_plays) > 0
                else 0
            )

            # Down and distance tendencies
            early_down_plays = team_plays[team_plays["down"].isin([1, 2])]
            early_down_rush_rate = (
                len(early_down_plays[early_down_plays["play_type"] == "run"])
                / len(early_down_plays)
                if len(early_down_plays) > 0
                else 0
            )

            short_yardage = team_plays[team_plays["ydstogo"] <= 3]
            short_yardage_rush_rate = (
                len(short_yardage[short_yardage["play_type"] == "run"])
                / len(short_yardage)
                if len(short_yardage) > 0
                else 0
            )

            # Pace metrics
            games_played = team_plays["game_id"].nunique()
            avg_plays_per_game = total_plays / games_played if games_played > 0 else 0

            # EPA and success metrics
            avg_rush_epa = rush_plays["epa"].mean() if len(rush_plays) > 0 else 0
            rush_success_rate = (
                (rush_plays["epa"] > 0).mean() if len(rush_plays) > 0 else 0
            )

            # Explosive play rates
            explosive_rushes = rush_plays[
                rush_plays["rushing_yards"] >= EXPLOSIVE_RUN_THRESHOLD
            ]
            explosive_rush_rate = (
                len(explosive_rushes) / len(rush_plays) if len(rush_plays) > 0 else 0
            )

            team_metrics.append(
                {
                    "team": team,
                    "total_plays": total_plays,
                    "games_played": games_played,
                    "rush_rate": rush_rate,
                    "rz_rush_rate": rz_rush_rate,
                    "gl_rush_rate": gl_rush_rate,
                    "leading_rush_rate": leading_rush_rate,
                    "trailing_rush_rate": trailing_rush_rate,
                    "early_down_rush_rate": early_down_rush_rate,
                    "short_yardage_rush_rate": short_yardage_rush_rate,
                    "avg_plays_per_game": avg_plays_per_game,
                    "avg_rush_epa": avg_rush_epa,
                    "rush_success_rate": rush_success_rate,
                    "explosive_rush_rate": explosive_rush_rate,
                }
            )

        return pd.DataFrame(team_metrics)

    def _calculate_defensive_metrics(self):
        """Calculate defensive metrics that affect RB matchups"""
        def_metrics = []

        for team in self.rb_plays["all_valid"]["defteam"].unique():
            def_plays = self.rb_plays["all_valid"][
                self.rb_plays["all_valid"]["defteam"] == team
            ]

            rush_plays_allowed = def_plays[def_plays["play_type"] == "run"]

            if len(rush_plays_allowed) == 0:
                continue

            # Basic defensive stats
            avg_rush_yards_allowed = rush_plays_allowed["rushing_yards"].mean()
            rush_epa_allowed = rush_plays_allowed["epa"].mean()
            rush_success_rate_allowed = (rush_plays_allowed["epa"] > 0).mean()

            # Situational defense
            rz_rush_allowed = rush_plays_allowed[
                rush_plays_allowed["yardline_100"] <= 20
            ]
            rz_rush_tds_allowed = rz_rush_allowed["rush_touchdown"].sum()
            rz_rush_attempts_allowed = len(rz_rush_allowed)

            # Explosive plays allowed
            explosive_rushes_allowed = rush_plays_allowed[
                rush_plays_allowed["rushing_yards"] >= EXPLOSIVE_RUN_THRESHOLD
            ]
            explosive_rush_rate_allowed = len(explosive_rushes_allowed) / len(
                rush_plays_allowed
            )

            # Yards after contact and other advanced metrics
            total_rush_yards_allowed = rush_plays_allowed["rushing_yards"].sum()

            # Stuff rate (negative or zero yard plays)
            stuffed_plays = rush_plays_allowed[rush_plays_allowed["rushing_yards"] <= 0]
            stuff_rate = len(stuffed_plays) / len(rush_plays_allowed)

            # Big play rate (15+ yards)
            big_plays_allowed = rush_plays_allowed[
                rush_plays_allowed["rushing_yards"] >= 15
            ]
            big_play_rate_allowed = len(big_plays_allowed) / len(rush_plays_allowed)

            def_metrics.append(
                {
                    "defense": team,
                    "rush_attempts_faced": len(rush_plays_allowed),
                    "total_rush_yards_allowed": total_rush_yards_allowed,
                    "avg_rush_yards_allowed": avg_rush_yards_allowed,
                    "rush_epa_allowed": rush_epa_allowed,
                    "rush_success_rate_allowed": rush_success_rate_allowed,
                    "rz_rush_tds_allowed": rz_rush_tds_allowed,
                    "rz_rush_attempts_allowed": rz_rush_attempts_allowed,
                    "explosive_rush_rate_allowed": explosive_rush_rate_allowed,
                    "big_play_rate_allowed": big_play_rate_allowed,
                    "stuff_rate": stuff_rate,
                }
            )

        return pd.DataFrame(def_metrics)

    def _build_rb_stats(self):
        """Build comprehensive RB stats from play-by-play data"""
        rb_stats = []

        # Process rushing stats
        rushing_stats = self._calculate_rushing_stats()

        # Process receiving stats
        receiving_stats = self._calculate_receiving_stats()

        # Combine stats
        all_players = set(rushing_stats.keys()) | set(receiving_stats.keys())

        for player_id in all_players:
            rush_data = rushing_stats.get(player_id, {})
            rec_data = receiving_stats.get(player_id, {})

            # Combine rushing and receiving
            player_stats = {
                "player_id": player_id,
                "player_name": rush_data.get("player_name")
                or rec_data.get("player_name"),
                "team": rush_data.get("team") or rec_data.get("team"),
                **rush_data,
                **rec_data,
            }

            # Calculate composite metrics
            player_stats["total_touches"] = player_stats.get(
                "rush_attempts", 0
            ) + player_stats.get("receptions", 0)
            player_stats["total_yards"] = player_stats.get(
                "rushing_yards", 0
            ) + player_stats.get("receiving_yards", 0)
            player_stats["total_tds"] = player_stats.get(
                "rushing_tds", 0
            ) + player_stats.get("receiving_tds", 0)

            if player_stats["total_touches"] > 0:
                player_stats["yards_per_touch"] = (
                    player_stats["total_yards"] / player_stats["total_touches"]
                )
            else:
                player_stats["yards_per_touch"] = 0

            # Fantasy points (PPR)
            player_stats["fantasy_points"] = (
                player_stats.get("rushing_yards", 0) * 0.1
                + player_stats.get("receiving_yards", 0) * 0.1
                + player_stats.get("total_tds", 0) * 6
                + player_stats.get("receptions", 0) * 1
            )

            games_played = player_stats.get("games_played", 1)
            player_stats["fantasy_ppg"] = player_stats["fantasy_points"] / games_played

            rb_stats.append(player_stats)

        self.rb_stats = pd.DataFrame(rb_stats)

        # Calculate team touch shares
        if not self.rb_stats.empty:
            team_touches = (
                self.rb_stats.groupby("team")["total_touches"].sum().reset_index()
            )
            team_touches.columns = ["team", "team_total_touches"]

            self.rb_stats = pd.merge(self.rb_stats, team_touches, on="team", how="left")
            self.rb_stats["team_touch_share"] = (
                self.rb_stats["total_touches"] / self.rb_stats["team_total_touches"]
            )

    def _calculate_rushing_stats(self):
        """Calculate detailed rushing stats from PBP data"""
        rushing_data = self.rb_plays["rushing"]
        rushing_stats = {}

        for player_id in rushing_data["rusher_id"].unique():
            player_plays = rushing_data[rushing_data["rusher_id"] == player_id]

            if len(player_plays) == 0:
                continue

            # Basic stats
            rush_attempts = len(player_plays)
            rushing_yards = player_plays["rushing_yards"].sum()
            rushing_tds = player_plays["rush_touchdown"].sum()

            # Advanced metrics
            rush_epa = player_plays["epa"].sum()
            avg_rush_epa = player_plays["epa"].mean()
            rush_success_rate = (player_plays["epa"] > 0).mean()

            # Situational usage
            rz_carries = len(player_plays[player_plays["yardline_100"] <= 20])
            goal_line_carries = len(player_plays[player_plays["yardline_100"] <= 5])

            # Explosive plays
            explosive_runs = len(
                player_plays[player_plays["rushing_yards"] >= EXPLOSIVE_RUN_THRESHOLD]
            )

            # Game script usage
            leading_carries = len(player_plays[player_plays["score_differential"] > 0])
            trailing_carries = len(player_plays[player_plays["score_differential"] < 0])

            games_played = player_plays["game_id"].nunique()

            rushing_stats[player_id] = {
                "player_name": player_plays["rusher_player_name"].iloc[0],
                "team": player_plays["posteam"].iloc[0],
                "games_played": games_played,
                "rush_attempts": rush_attempts,
                "rushing_yards": rushing_yards,
                "rushing_tds": rushing_tds,
                "yards_per_carry": (
                    rushing_yards / rush_attempts if rush_attempts > 0 else 0
                ),
                "rush_epa": rush_epa,
                "avg_rush_epa": avg_rush_epa,
                "rush_success_rate": rush_success_rate,
                "rz_carries": rz_carries,
                "goal_line_carries": goal_line_carries,
                "explosive_runs": explosive_runs,
                "leading_carries": leading_carries,
                "trailing_carries": trailing_carries,
                "carries_per_game": rush_attempts / games_played,
            }

        return rushing_stats

    def _calculate_receiving_stats(self):
        """Calculate receiving stats for RBs from PBP data"""
        receiving_data = self.rb_plays["receiving"]
        receiving_stats = {}

        # This is a simplified version - in reality you'd want to identify RBs by position
        # For now, we'll use players who also have rushing attempts
        rb_rushers = set(self.rb_plays["rushing"]["rusher_id"].unique())

        for player_id in receiving_data["receiver_id"].unique():
            # Only include if they're also a rusher (simple RB identification)
            if player_id not in rb_rushers:
                continue

            player_plays = receiving_data[receiving_data["receiver_id"] == player_id]

            if len(player_plays) == 0:
                continue

            # Basic receiving stats
            targets = len(player_plays)
            receptions = player_plays["complete_pass"].sum()
            receiving_yards = player_plays["receiving_yards"].fillna(0).sum()
            receiving_tds = player_plays["pass_touchdown"].sum()

            # Advanced metrics
            catch_rate = receptions / targets if targets > 0 else 0
            yards_per_target = receiving_yards / targets if targets > 0 else 0
            yards_per_reception = receiving_yards / receptions if receptions > 0 else 0

            # Air yards and YAC
            air_yards = player_plays["air_yards"].fillna(0).sum()
            yac = player_plays["yards_after_catch"].fillna(0).sum()

            games_played = player_plays["game_id"].nunique()

            receiving_stats[player_id] = {
                "targets": targets,
                "receptions": receptions,
                "receiving_yards": receiving_yards,
                "receiving_tds": receiving_tds,
                "catch_rate": catch_rate,
                "yards_per_target": yards_per_target,
                "yards_per_reception": yards_per_reception,
                "air_yards": air_yards,
                "yac": yac,
                "targets_per_game": targets / games_played,
            }

        return receiving_stats

    def project_weekly_fantasy(self, week_num: int, filters: Optional[Dict] = None):
        """Project fantasy points for a specific week with advanced filtering"""
        if self.rb_stats is None:
            raise ValueError("Must load data first!")

        # Apply filters if provided
        filtered_stats = self.rb_stats.copy()
        if filters:
            for column, condition in filters.items():
                if column in filtered_stats.columns:
                    filtered_stats = filtered_stats[condition(filtered_stats[column])]

        # Get matchups for the week
        week_games = self.schedules[self.schedules["week"] == week_num].copy()

        projections = []

        for _, player in filtered_stats.iterrows():
            # Skip players with minimal usage
            if player["total_touches"] < 5:
                continue

            # Find their matchup
            team = player["team"]
            matchup = week_games[
                (week_games["home_team"] == team) | (week_games["away_team"] == team)
            ]

            if matchup.empty:
                continue  # Bye week

            opponent = (
                matchup.iloc[0]["away_team"]
                if matchup.iloc[0]["home_team"] == team
                else matchup.iloc[0]["home_team"]
            )

            # Base projection from recent performance
            base_projection = player["fantasy_ppg"]

            # Matchup adjustments
            matchup_modifier = self._calculate_matchup_modifier(team, opponent)

            # Game environment adjustments
            pace_modifier = self._calculate_pace_modifier(team)

            # Final projection
            projected_points = base_projection * matchup_modifier * pace_modifier

            projections.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["player_name"],
                    "team": team,
                    "opponent": opponent,
                    "projected_points": projected_points,
                    "base_ppg": base_projection,
                    "matchup_modifier": matchup_modifier,
                    "pace_modifier": pace_modifier,
                    "total_touches": player["total_touches"],
                    "team_touch_share": player["team_touch_share"],
                    "yards_per_touch": player["yards_per_touch"],
                    "rush_success_rate": player.get("rush_success_rate", 0),
                    "explosive_runs": player.get("explosive_runs", 0),
                }
            )

        return pd.DataFrame(projections).sort_values(
            "projected_points", ascending=False
        )

    def _calculate_matchup_modifier(self, team: str, opponent: str) -> float:
        """Calculate matchup difficulty modifier based on opposing defense EPA"""
        if (
            self.defensive_stats is None
            or opponent not in self.defensive_stats["defense"].values
        ):
            return 1.0

        opp_def = self.defensive_stats[self.defensive_stats["defense"] == opponent]
        if opp_def.empty:
            return 1.0

        # Primary modifier based on EPA allowed (more predictive than yards)
        league_avg_epa = self.defensive_stats["rush_epa_allowed"].mean()
        opp_epa_allowed = opp_def["rush_epa_allowed"].iloc[0]

        # Higher EPA allowed = easier matchup (positive modifier)
        # Lower EPA allowed = harder matchup (negative modifier)
        if league_avg_epa != 0:
            epa_modifier = opp_epa_allowed / league_avg_epa
        else:
            epa_modifier = 1.0

        # Secondary modifier based on success rate allowed
        league_avg_success = self.defensive_stats["rush_success_rate_allowed"].mean()
        opp_success_allowed = opp_def["rush_success_rate_allowed"].iloc[0]

        if league_avg_success != 0:
            success_modifier = opp_success_allowed / league_avg_success
        else:
            success_modifier = 1.0

        # Combine EPA (70% weight) and success rate (30% weight)
        combined_modifier = (epa_modifier * 0.7) + (success_modifier * 0.3)

        # Cap modifier between 0.6 and 1.4 for more realistic range
        return max(0.6, min(1.4, combined_modifier))

    def _calculate_pace_modifier(self, team: str) -> float:
        """Calculate pace-based modifier"""
        if self.team_stats is None or team not in self.team_stats["team"].values:
            return 1.0

        team_data = self.team_stats[self.team_stats["team"] == team]
        if team_data.empty:
            return 1.0

        team_pace = team_data["avg_plays_per_game"].iloc[0]
        league_avg_pace = self.team_stats["avg_plays_per_game"].mean()

        return team_pace / league_avg_pace

    def get_top_plays(
        self, week_num: int, min_projection: float = 8.0, filters: Optional[Dict] = None
    ):
        """Get recommended RB plays with advanced filtering"""
        projections = self.project_weekly_fantasy(week_num, filters)

        top_plays = projections[
            projections["projected_points"] >= min_projection
        ].copy()

        # Add confidence levels
        top_plays["confidence"] = np.where(
            top_plays["team_touch_share"] > 0.6,
            "High",
            np.where(top_plays["team_touch_share"] > 0.3, "Medium", "Low"),
        )

        return top_plays[
            [
                "player_name",
                "team",
                "opponent",
                "projected_points",
                "confidence",
                "team_touch_share",
                "yards_per_touch",
                "rush_success_rate",
                "explosive_runs",
            ]
        ]

    def get_matchup_analysis(self, week_num: int, player_name: str = None):
        """Get detailed matchup analysis for a specific week or player"""
        if self.defensive_stats is None or self.team_stats is None:
            raise ValueError("Must load data first!")

        week_games = self.schedules[self.schedules["week"] == week_num].copy()
        matchup_data = []

        for _, game in week_games.iterrows():
            home_team = game["home_team"]
            away_team = game["away_team"]

            # Home team vs away defense
            away_def = self.defensive_stats[
                self.defensive_stats["defense"] == away_team
            ]
            if not away_def.empty:
                matchup_data.append(
                    {
                        "offense": home_team,
                        "defense": away_team,
                        "location": "Home",
                        "def_epa_allowed": away_def["rush_epa_allowed"].iloc[0],
                        "def_success_rate_allowed": away_def[
                            "rush_success_rate_allowed"
                        ].iloc[0],
                        "def_explosive_rate_allowed": away_def[
                            "explosive_rush_rate_allowed"
                        ].iloc[0],
                        "def_stuff_rate": away_def["stuff_rate"].iloc[0],
                        "matchup_modifier": self._calculate_matchup_modifier(
                            home_team, away_team
                        ),
                    }
                )

            # Away team vs home defense
            home_def = self.defensive_stats[
                self.defensive_stats["defense"] == home_team
            ]
            if not home_def.empty:
                matchup_data.append(
                    {
                        "offense": away_team,
                        "defense": home_team,
                        "location": "Away",
                        "def_epa_allowed": home_def["rush_epa_allowed"].iloc[0],
                        "def_success_rate_allowed": home_def[
                            "rush_success_rate_allowed"
                        ].iloc[0],
                        "def_explosive_rate_allowed": home_def[
                            "explosive_rush_rate_allowed"
                        ].iloc[0],
                        "def_stuff_rate": home_def["stuff_rate"].iloc[0],
                        "matchup_modifier": self._calculate_matchup_modifier(
                            away_team, home_team
                        ),
                    }
                )

        matchups_df = pd.DataFrame(matchup_data)

        if player_name:
            # Filter to specific player's team
            if self.rb_stats is not None:
                player_team = self.rb_stats[
                    self.rb_stats["player_name"].str.contains(
                        player_name, case=False, na=False
                    )
                ]
                if not player_team.empty:
                    team = player_team["team"].iloc[0]
                    matchups_df = matchups_df[matchups_df["offense"] == team]

        return matchups_df.sort_values("matchup_modifier", ascending=False)

    def run_full_analysis(
        self,
        target_week: int,
        weeks_filter: Optional[List[int]] = None,
        filters: Optional[Dict] = None,
    ):
        """Run complete PBP-based analysis pipeline"""
        print(f"Running PBP RB Fantasy Analysis for Week {target_week}")
        print("=" * 60)

        # Load and process data
        self.load_data(weeks_filter)

        # Get projections
        projections = self.project_weekly_fantasy(target_week, filters)
        top_plays = self.get_top_plays(target_week, filters=filters)

        # Display results
        print(f"\nTop RB Plays for Week {target_week}:")
        if not top_plays.empty:
            print(top_plays.head(10).to_string(index=False))
        else:
            print("No players meet the criteria")

        print(f"\nHigh-Confidence Plays (>60% team touch share):")
        high_conf = top_plays[top_plays["confidence"] == "High"]
        if not high_conf.empty:
            print(high_conf.to_string(index=False))
        else:
            print("No high-confidence plays found")

        return projections, top_plays


# Example usage with advanced filtering
if __name__ == "__main__":
    # Initialize projector
    projector = PBPRBFantasyProjector(current_season=2024)

    # Example filters
    example_filters = {
        "total_touches": lambda x: x >= 20,  # At least 20 touches
        "team_touch_share": lambda x: x >= 0.2,  # At least 20% team share
        "rush_success_rate": lambda x: x >= 0.4,  # At least 40% success rate
    }

    # Run analysis with recent weeks only
    target_week = 8
    recent_weeks = [1, 2, 3, 4, 5, 6, 7]  # Use first 7 weeks as sample

    projections, top_plays = projector.run_full_analysis(
        target_week=target_week, weeks_filter=recent_weeks, filters=example_filters
    )
