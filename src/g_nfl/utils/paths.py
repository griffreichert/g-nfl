from pathlib import Path

PROJECT_DIR = Path(__file__).parents[3]

LOGO_PATH = PROJECT_DIR / "bin" / "logos"

DATA_PATH = PROJECT_DIR / "data"

HOMERS_PATH = DATA_PATH / "homers"

INPREDICABLE_PATH = DATA_PATH / "inpredictable"

NFELO_PATH = DATA_PATH / "nfelo"

SUMER_PATH = DATA_PATH / "sumer"
SUMER_ELO_PATH = SUMER_PATH / "elo"
SUMER_OFFENSE_PATH = SUMER_PATH / "offense"
SUMER_DEFENSE_PATH = SUMER_PATH / "defense"
SUMER_PLAYER_PATH = SUMER_PATH / "player"

UNABATED_PATH = DATA_PATH / "unabated"

ESPN_PATH = DATA_PATH / "espn"
