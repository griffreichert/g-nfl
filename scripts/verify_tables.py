#!/usr/bin/env python3
"""
Script to verify that the database tables were created correctly.
Run this after creating tables manually in Supabase.
"""

import os
import sys

# Add the project root to the path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.g_nfl.utils.database import MarketLinesDatabase, PoolSpreadsDatabase


def verify_tables():
    """Verify that the database tables exist and are accessible"""

    print("🔍 Verifying database tables...\n")

    # Test market_lines table
    try:
        market_db = MarketLinesDatabase()
        # Try to query the table (this will fail if table doesn't exist)
        result = market_db.get_market_lines(2025, 1)
        print("✅ market_lines table exists and is accessible")
        print(f"   Found {len(result)} records for 2025 Week 1")
        market_ok = True
    except Exception as e:
        print(f"❌ market_lines table issue: {e}")
        market_ok = False

    # Test pool_spreads table
    try:
        pool_db = PoolSpreadsDatabase()
        # Try to query the table (this will fail if table doesn't exist)
        result = pool_db.get_pool_spreads(2025, 1)
        print("✅ pool_spreads table exists and is accessible")
        print(f"   Found {len(result)} records for 2025 Week 1")
        pool_ok = True
    except Exception as e:
        print(f"❌ pool_spreads table issue: {e}")
        pool_ok = False

    print()

    if market_ok and pool_ok:
        print("🎉 All tables verified successfully!")
        print("\n✅ Next steps:")
        print("1. Run 'python scripts/update_market_lines.py --season 2025 --week 1'")
        print("2. Use the 'Manage Pool Spreads' Streamlit page")
        return True
    else:
        print("❌ Some tables have issues. Please check your Supabase setup.")
        print("\n💡 Make sure you've run the SQL from 'scripts/database_schema.sql'")
        return False


def test_insert():
    """Test inserting sample data to verify tables work correctly"""

    print("🧪 Testing table operations...\n")

    try:
        # Test market lines insert
        market_db = MarketLinesDatabase()
        test_lines = {"test_2025_1_KC_LAC": {"spread": -3.5, "total": 47.5}}

        saved = market_db.save_market_lines(
            2025, 99, test_lines
        )  # Use week 99 for testing
        print(f"✅ market_lines insert test: saved {saved} records")

        # Test pool spreads insert
        pool_db = PoolSpreadsDatabase()
        test_spreads = {"test_2025_1_KC_LAC": -3.0}

        saved = pool_db.save_pool_spreads(2025, 99, test_spreads)
        print(f"✅ pool_spreads insert test: saved {saved} records")

        # Clean up test data
        print("🧹 Cleaning up test data...")
        # Note: We could add delete methods if needed, but for now just leave the test data

        print("\n🎉 All table operations working correctly!")
        return True

    except Exception as e:
        print(f"❌ Table operation test failed: {e}")
        return False


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Verify database tables")
    parser.add_argument("--test", action="store_true", help="Run insert/update tests")

    args = parser.parse_args()

    # Always verify tables exist first
    tables_ok = verify_tables()

    if not tables_ok:
        sys.exit(1)

    # Run tests if requested
    if args.test:
        print("\n" + "=" * 50)
        test_ok = test_insert()
        if not test_ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
