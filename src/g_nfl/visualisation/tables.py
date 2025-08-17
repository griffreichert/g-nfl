from matplotlib.colors import LinearSegmentedColormap

# Create a custom colormap from purple to white to green
pg_cmap = LinearSegmentedColormap.from_list(
    "green_white_purple", ["green", "white", "purple"]
)
