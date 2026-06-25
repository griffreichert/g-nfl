import warnings

import nflreadpy as nfl
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


class RBFantasyProjector:
    def __init__(self, current_season=2024):
        self.current_season = current_season
        self.player_stats = None
        self.team_stats = None
        self.schedules = None
        self.ros_projections = None

    def load_data(self):
        """Load all necessary data from nflreadpy"""
        print("Loading player stats...")
        # ponytail: .to_pandas() — entire class is pandas; porting out of scope for this migration
        # load_player_stats(summary_level='reg') already includes position, player_name, recent_team
        # so the old import_seasonal_rosters merge is no longer needed
        player_data = nfl.load_player_stats(
            seasons=[self.current_season], summary_level="reg"
        ).to_pandas()

        print(f"Available positions: {player_data['position'].unique()}")

        # Filter for RBs
        self.rb_stats = player_data[player_data["position"] == "RB"].copy()

        if len(self.rb_stats) == 0:
            print("No RBs found! Trying 'HB' instead...")
            self.rb_stats = player_data[player_data["position"] == "HB"].copy()

        print(f"Found {len(self.rb_stats)} RBs")

        # Fill NaN values with 0 for receiving stats (some RBs have no targets)
        receiving_cols = ["receptions", "targets", "receiving_yards", "receiving_tds"]
        for col in receiving_cols:
            if col in self.rb_stats.columns:
                self.rb_stats[col] = self.rb_stats[col].fillna(0)

        print("Loading team stats...")
        pbp_data = nfl.load_pbp(seasons=[self.current_season]).to_pandas()
        self.team_stats = self._calculate_team_metrics(pbp_data)

        print("Loading schedules...")
        self.schedules = nfl.load_schedules(seasons=[self.current_season]).to_pandas()

        print("Data loading complete!")

    def _calculate_team_metrics(self, pbp_data):
        """Calculate team-level metrics that affect RB production"""
        team_metrics = []

        for team in pbp_data["posteam"].dropna().unique():
            team_plays = pbp_data[pbp_data["posteam"] == team]

            # Offensive metrics
            total_plays = len(team_plays)
            rush_attempts = len(team_plays[team_plays["play_type"] == "run"])
            rush_rate = rush_attempts / total_plays if total_plays > 0 else 0

            # Red zone usage
            rz_plays = team_plays[team_plays["yardline_100"] <= 20]
            rz_rush_rate = (
                len(rz_plays[rz_plays["play_type"] == "run"]) / len(rz_plays)
                if len(rz_plays) > 0
                else 0
            )

            # Game script tendency (when leading/trailing)
            leading_plays = team_plays[team_plays["score_differential"] > 0]
            leading_rush_rate = (
                len(leading_plays[leading_plays["play_type"] == "run"])
                / len(leading_plays)
                if len(leading_plays) > 0
                else 0
            )

            team_metrics.append(
                {
                    "team": team,
                    "total_plays": total_plays,
                    "rush_rate": rush_rate,
                    "rz_rush_rate": rz_rush_rate,
                    "leading_rush_rate": leading_rush_rate,
                    "avg_plays_per_game": total_plays / 17,  # Assuming 17 games
                }
            )

        return pd.DataFrame(team_metrics)

    def calculate_usage_metrics(self):
        """Calculate key usage metrics for each RB"""
        if self.rb_stats is None:
            raise ValueError("Must load data first!")

        # Calculate snap share approximation and usage rates
        self.rb_stats["total_touches"] = (
            self.rb_stats["carries"] + self.rb_stats["receptions"]
        )
        self.rb_stats["total_yards"] = (
            self.rb_stats["rushing_yards"] + self.rb_stats["receiving_yards"]
        )
        self.rb_stats["total_tds"] = (
            self.rb_stats["rushing_tds"] + self.rb_stats["receiving_tds"]
        )

        # Yards per touch efficiency
        self.rb_stats["yards_per_touch"] = np.where(
            self.rb_stats["total_touches"] > 0,
            self.rb_stats["total_yards"] / self.rb_stats["total_touches"],
            0,
        )

        # Target share (receiving involvement)
        self.rb_stats["target_share"] = np.where(
            self.rb_stats["targets"] > 0,
            self.rb_stats["targets"] / self.rb_stats["games"],  # targets per game
            0,
        )

        # Calculate team-level touch share
        team_touches = (
            self.rb_stats.groupby("recent_team")["total_touches"].sum().reset_index()
        )
        team_touches.columns = ["recent_team", "team_total_touches"]

        self.rb_stats = pd.merge(
            self.rb_stats, team_touches, on="recent_team", how="left"
        )
        self.rb_stats["team_touch_share"] = (
            self.rb_stats["total_touches"] / self.rb_stats["team_total_touches"]
        )

        # Fantasy points per game (standard scoring)
        self.rb_stats["fantasy_ppg"] = (
            self.rb_stats["rushing_yards"] * 0.1
            + self.rb_stats["receiving_yards"] * 0.1
            + self.rb_stats["total_tds"] * 6
            + self.rb_stats["receptions"] * 1  # PPR
        ) / self.rb_stats["games"]

        return self.rb_stats

    def project_weekly_fantasy(self, week_num):
        """Project fantasy points for a specific week"""
        if self.rb_stats is None:
            raise ValueError("Must calculate usage metrics first!")

        # Get matchups for the week
        week_games = self.schedules[self.schedules["week"] == week_num].copy()

        projections = []

        for _, player in self.rb_stats.iterrows():
            # Skip players with minimal usage
            if player["total_touches"] < 10:
                continue

            # Find their matchup
            team = player["recent_team"]
            matchup = week_games[
                (week_games["home_team"] == team) | (week_games["away_team"] == team)
            ]

            if matchup.empty:
                continue  # Bye week or no matchup found

            opponent = (
                matchup.iloc[0]["away_team"]
                if matchup.iloc[0]["home_team"] == team
                else matchup.iloc[0]["home_team"]
            )

            # Base projection from season averages
            base_projection = player["fantasy_ppg"]

            # Adjust for matchup difficulty (placeholder - you'd want defensive rankings here)
            matchup_modifier = 1.0  # Neutral for now

            # Adjust for game environment
            team_pace = (
                self.team_stats[self.team_stats["team"] == team][
                    "avg_plays_per_game"
                ].iloc[0]
                if len(self.team_stats[self.team_stats["team"] == team]) > 0
                else 65
            )
            pace_modifier = team_pace / 65  # League average ~65 plays

            # Final projection
            projected_points = base_projection * matchup_modifier * pace_modifier

            projections.append(
                {
                    "player_name": player["player_name"],
                    "team": team,
                    "opponent": opponent,
                    "projected_points": projected_points,
                    "total_touches": player["total_touches"],
                    "fantasy_ppg": player["fantasy_ppg"],
                    "yards_per_touch": player["yards_per_touch"],
                    "team_touch_share": player["team_touch_share"],
                }
            )

        return pd.DataFrame(projections).sort_values(
            "projected_points", ascending=False
        )

    def get_top_plays(self, week_num, min_projection=8.0):
        """Get recommended RB plays for the week"""
        projections = self.project_weekly_fantasy(week_num)

        top_plays = projections[
            projections["projected_points"] >= min_projection
        ].copy()

        # Add confidence levels based on usage
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
                "yards_per_touch",
            ]
        ]

    def run_full_analysis(self, target_week):
        """Run complete analysis pipeline"""
        print(f"Running RB Fantasy Analysis for Week {target_week}")
        print("=" * 50)

        # Load and process data
        self.load_data()
        self.calculate_usage_metrics()

        # Get projections
        projections = self.project_weekly_fantasy(target_week)
        top_plays = self.get_top_plays(target_week)

        # Display results
        print(f"\nTop RB Plays for Week {target_week}:")
        print(top_plays.head(10).to_string(index=False))

        print("\nHigh-Confidence Plays (>60% team touch share):")
        high_conf = top_plays[top_plays["confidence"] == "High"]
        print(high_conf.to_string(index=False))

        return projections, top_plays


# Example usage:
if __name__ == "__main__":
    # Initialize projector
    projector = RBFantasyProjector(current_season=2024)

    # Run analysis for next week (adjust as needed)
    target_week = 8  # Change this to current week
    projections, top_plays = projector.run_full_analysis(target_week)

    # You can also get individual components:
    # projector.load_data()
    # rb_stats = projector.calculate_usage_metrics()
    # week_projections = projector.project_weekly_fantasy(target_week)
