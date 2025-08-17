import os

import requests

from g_nfl.utils.paths import LOGO_PATH

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
    }
    team = team_map.get(team, team)
    assert team in nfl_teams, print(team, "not in dict")
    return team


def download_team_pngs():
    # Base URL for the team logos and local directory
    base_url = "https://a.espncdn.com/i/teamlogos/nfl/500/"

    # Create the local directory if it doesn't exist
    if not os.path.exists(LOGO_PATH):
        os.makedirs(LOGO_PATH)

    # Iterate through the list of teams, download logos, and save them locally
    for team in nfl_teams:
        team = team.lower()
        url = f"{base_url}{team}.png"
        response = requests.get(url)
        if response.status_code == 200:
            # Save the image to the local directory
            with open(LOGO_PATH / f"{team}.png", "wb") as file:
                file.write(response.content)
        else:
            print(f"Failed to download logo for {team}")
    print(f"Logos downloaded to {LOGO_PATH}")
