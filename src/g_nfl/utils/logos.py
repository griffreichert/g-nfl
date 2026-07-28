import urllib.request

import nflreadpy as nfl
import numpy as np
from matplotlib.offsetbox import OffsetImage
from PIL import Image

from g_nfl.utils.paths import LOGO_PATH
from g_nfl.utils.teams import nfl_teams

espn_logo_url = "https://a.espncdn.com/i/teamlogos/nfl/500/{team}.png"


def get_logo_url(team: str, size: int = 25):
    assert team.upper() in nfl_teams
    return f'<img src="{espn_logo_url.format(team=team)}" style="width:auto;height:{size}px;">'


def fetch_logos():
    LOGO_PATH.mkdir(parents=True, exist_ok=True)
    logos = nfl.load_teams().select(["team_abbr", "team_logo_espn"])

    # only fetch teams whose logo is missing so a partial/empty dir gets topped up
    missing = [
        (team, logo_url)
        for team, logo_url in logos.iter_rows()
        if not (LOGO_PATH / f"{team}.png").exists()
    ]
    if not missing:
        return

    print("fetching team logos...")
    for team, logo_url in missing:
        urllib.request.urlretrieve(logo_url, LOGO_PATH / f"{team}.png")
    print("successfully retrieved logos")


def get_team_logo(
    team: str, size: tuple[int, int] = (50, 50), alpha: float = 1.0
) -> OffsetImage:
    team = team.upper()
    # Open the image with PIL and resize it
    image = Image.open(str(LOGO_PATH / f"{team}.png"))
    image = image.resize(size, Image.Resampling.LANCZOS)
    return OffsetImage(np.asarray(image), alpha=alpha, zoom=1.0)
