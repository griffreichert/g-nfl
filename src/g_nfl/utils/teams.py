nfl_teams = {
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LA",
    "LAC",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
}


def get_nfl_teams() -> list:
    # list(sorted(nfl.import_schedules([2023]).away_team.unique()))
    return list(nfl_teams)


def standardize_teams(team):
    team_map = {
        "ARZ": "ARI",
        "BLT": "BAL",
        "CLV": "CLE",
        "HST": "HOU",
        "JAG": "JAX",
        "JAC": "JAX",
        "LAR": "LA",
        "PHL": "PHI",
        "WSH": "WAS",
        "WFT": "WAS",
        # franchise relocations: historic draft/roster data pre-move
        "OAK": "LV",
        "SD": "LAC",
        "STL": "LA",
        # nflreadpy draft_picks uses PFR-style 3-letter codes
        "GNB": "GB",
        "KAN": "KC",
        "LVR": "LV",
        "NOR": "NO",
        "NWE": "NE",
        "SDG": "LAC",
        "SFO": "SF",
        "TAM": "TB",
    }
    team = team_map.get(team, team)
    assert team in nfl_teams, print(team, "not in dict")
    return team
