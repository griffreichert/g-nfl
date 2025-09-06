#!/usr/bin/env python3
"""
Script to prepare the app for deployment.
Generates requirements.txt from poetry dependencies.
"""

import os
import subprocess
import sys


def main():
    """Prepare the app for deployment"""

    print("🚀 Preparing app for deployment...\n")

    # Generate requirements.txt from poetry
    print("📦 Generating requirements.txt from poetry dependencies...")
    try:
        result = subprocess.run(
            [
                "poetry",
                "export",
                "-f",
                "requirements.txt",
                "--output",
                "requirements.txt",
                "--without-hashes",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print("✅ requirements.txt generated successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate requirements.txt: {e}")
        print(f"STDERR: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Poetry not found. Make sure poetry is installed.")
        sys.exit(1)

    # Check if app entry point exists
    app_main = os.path.join("app", "main.py")
    if os.path.exists(app_main):
        print("✅ App entry point found at app/main.py")
    else:
        print("❌ App entry point not found. Expected app/main.py")
        sys.exit(1)

    print("\n🎉 Deployment preparation complete!")
    print("\n📝 Next steps for Streamlit Cloud deployment:")
    print("1. Commit and push your changes to GitHub")
    print("2. Go to https://share.streamlit.io/")
    print("3. Connect your GitHub repo")
    print("4. Set main file path to: app/main.py")
    print("5. Make sure your environment variables are set in Streamlit Cloud")
    print("\n🔧 Required environment variables:")
    print("- SUPABASE_URL")
    print("- SUPABASE_KEY")


if __name__ == "__main__":
    main()
