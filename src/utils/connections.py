from gspread.auth import service_account
from gspread.client import Client

from src.utils.paths import PROJECT_DIR


def load_service_account() -> Client:
    """Load the google service account from the json file

    Returns
    -------
    Client
        google service account client
    """
    return service_account(filename=PROJECT_DIR / "google_config.json")
