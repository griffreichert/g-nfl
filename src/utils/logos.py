import os
import urllib.request
from typing import Tuple

import nfl_data_py as nfl
import numpy as np
import pandas as pd
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from PIL import Image

from src.utils.paths import LOGO_PATH

espn_logo_url = "https://a.espncdn.com/i/teamlogos/nfl/500/{team}.png"


def fetch_logos():
    # if the path to the logos directory does not exist, create it
    if not os.path.exists(LOGO_PATH):
        print("fetching team logos...")
        os.makedirs(LOGO_PATH, exist_ok=True)
        logos = nfl.import_team_desc()[["team_abbr", "team_logo_espn"]]

        # get the logos for each team and store them to tif files in the logo path directory "<team>.tif"
        for _, team, logo_url in logos.itertuples():
            urllib.request.urlretrieve(logo_url, LOGO_PATH / f"{team}.tif")
        print("successfully retrieved logos")


def get_team_logo(
    team: str, size: Tuple[int, int] = (50, 50), alpha: float = 1.0
) -> OffsetImage:
    # Open the image with PIL and resize it
    image = Image.open(str(LOGO_PATH / f"{team}.tif"))
    image = image.resize(size, Image.Resampling.LANCZOS)
    return OffsetImage(np.asarray(image), alpha=alpha, zoom=1.0)
