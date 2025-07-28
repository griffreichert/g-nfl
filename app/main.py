import os
import subprocess
import sys


def run_app():
    """Entry point for running the Streamlit app"""
    app_path = os.path.join(os.path.dirname(__file__), "streamlit_app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])


if __name__ == "__main__":
    run_app()
