#!/usr/bin/env python3
"""
Simple script to clear all action pricing data from the database.
This version uses direct psycopg2 connection without async.
"""
import os
import sys

# Try to import psycopg2 or psycopg2-binary
try:
    import psycopg2
except ImportError:
    print("psycopg2 not found. Please install it with: pip install psycopg2-binary")
    sys.exit(1)


def clear_action_pricing():
    """Delete all rows from the action_pricing table."""
    # Get database URL from environment or use default
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("DATABASE_URL environment variable not set")
        print("Please set it or pass it as an argument")
        print(
            "Example: DATABASE_URL=postgresql://user:pass@host:port/dbname python clear_action_pricing_simple.py"
        )
        sys.exit(1)

    conn = None
    cursor = None

    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # Count existing records first
        cursor.execute("SELECT COUNT(*) FROM action_pricing")
        count = cursor.fetchone()[0]
        print(f"Found {count} existing action pricing records")

        if count > 0:
            # Delete all records
            cursor.execute("DELETE FROM action_pricing")
            conn.commit()
            print(f"Successfully deleted all {count} records from action_pricing table")
        else:
            print("action_pricing table is already empty")

        # Verify the table is empty
        cursor.execute("SELECT COUNT(*) FROM action_pricing")
        final_count = cursor.fetchone()[0]
        print(f"Verification: action_pricing table now contains {final_count} records")

    except Exception as e:
        print(f"Error clearing action_pricing table: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    clear_action_pricing()
