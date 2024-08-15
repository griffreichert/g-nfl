# df.columns = flatten_grouped_cols(df.columns)
flatten_grouped_cols = lambda cols: list(map("_".join, cols))
