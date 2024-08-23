# df.columns = flatten_grouped_cols(df.columns)
flatten_grouped_cols = lambda cols: list(map("_".join, cols))
coach_lambda = lambda row: (
    row["home_coach"] if row["posteam"] == row["home_team"] else row["away_coach"]
)
