#!/usr/bin/env python3
"""
Script to create the required database tables in Supabase.
Run this once to set up the market_lines and pool_spreads tables.
"""

import os
import sys

# Add the project root to the path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.g_nfl.utils.supabase_client import get_supabase


def create_tables():
    """Create the required database tables"""

    print("❌ Automated table creation through Python is not reliable.")
    print("\n💡 Please create the tables manually using the Supabase Dashboard:")
    print("\n📝 Steps:")
    print("1. Go to your Supabase Dashboard")
    print("2. Navigate to the SQL Editor")
    print("3. Copy and paste the contents of 'scripts/database_schema.sql'")
    print("4. Click 'Run' to execute the SQL")
    print("\nAlternatively, copy this SQL and run it directly:\n")

    sql_file_path = os.path.join(os.path.dirname(__file__), "database_schema.sql")
    try:
        with open(sql_file_path, "r") as f:
            sql_content = f.read()
        print("=" * 60)
        print(sql_content)
        print("=" * 60)
    except FileNotFoundError:
        print("❌ Could not find database_schema.sql file")

    return False


def check_existing_tables():
    """Check if tables already exist"""
    client = get_supabase()

    try:
        # Check if tables exist by trying to select from them
        print("Checking existing tables...")

        try:
            market_result = client.table("market_lines").select("id").limit(1).execute()
            print("✅ market_lines table exists")
            market_exists = True
        except:
            print("❌ market_lines table does not exist")
            market_exists = False

        try:
            pool_result = client.table("pool_spreads").select("id").limit(1).execute()
            print("✅ pool_spreads table exists")
            pool_exists = True
        except:
            print("❌ pool_spreads table does not exist")
            pool_exists = False

        return market_exists, pool_exists

    except Exception as e:
        print(f"Error checking tables: {e}")
        return False, False


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create database tables for market lines and pool spreads"
    )
    parser.add_argument(
        "--check", action="store_true", help="Check if tables already exist"
    )
    parser.add_argument(
        "--force", action="store_true", help="Create tables even if they exist"
    )

    args = parser.parse_args()

    if args.check:
        print("🔍 Checking existing database tables...\n")
        market_exists, pool_exists = check_existing_tables()

        if market_exists and pool_exists:
            print("\n✅ All required tables already exist!")
        else:
            print(f"\n⚠️  Missing tables detected. Run without --check to create them.")
        return

    # Check if tables exist (unless forced)
    if not args.force:
        print("🔍 Checking for existing tables...\n")
        market_exists, pool_exists = check_existing_tables()

        if market_exists and pool_exists:
            print("\n⚠️  Tables already exist! Use --force to recreate them.")
            return
        print()

    # Create tables
    print("🔨 Creating database tables...\n")
    success = create_tables()

    if success:
        print("\n🚀 Database setup complete! You can now:")
        print(
            "1. Run 'python scripts/update_market_lines.py --season 2025 --week 1' to load market data"
        )
        print("2. Use the 'Manage Pool Spreads' page to set competition spreads")
        print("3. Make picks with the new spread display!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
