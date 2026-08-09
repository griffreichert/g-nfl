CUR_SEASON = 2025
CUR_WEEK = 12

# Home-field advantage in points. Realized 2016-23 mean home margin ~2.1, but
# HFA has been declining post-2020; 1.5 ~ recent seasons.
HFA = 1.5
AVG_POINTS = 21.5

# Std of home margin. Realized ~14 (REG 2016-23), ~13.3 trimmed of blowouts.
# (Was a stale 11.5, which made percentile->spread conversions too narrow.)
SPREAD_STDEV = 13.5

# Win probability threshold to limit garbage time
DEFAULT_WIN_PROB = 0.05

# Define thresholds for explosive plays
EXPLOSIVE_RUN_THRESHOLD = 10
EXPLOSIVE_PASS_THRESHOLD = 15

# Pickers in the no-homers pool. TEST is a scratch profile for exercising the
# save path without writing to anyone's real record; the team board treats it
# as non-voting so it never lands in the consensus.
PICKERS = [
    "TEAM",
    "Griffin",
    "Harry",
    "Ben",
    "Chuck",
    "Hunter",
    "bModel",
    "gModel",
    "TEST",
]
# Scratch profile: it can save picks, but it is not a competitor and never
# appears in standings or in the team board's consensus.
TEST_PICKER = "TEST"

# Survivor pool used teams - teams that have already been picked and cannot be used again
# Update this list each week after making survivor picks
SURVIVOR_USED_TEAMS = [
    "HOU",
    "KC",
    "BAL",
    "SEA",
    "GB",
    "IND",
    "LA",
    "DET",
    "ARI",
    "DEN",
]
