"""Play-by-play and schedule loaders with a local parquet cache.

Implemented in #9. Wraps `nflreadpy` so the rest of the pipeline never
touches the network layer directly.
"""
