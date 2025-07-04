#!/usr/bin/env python3
"""
Script to clear all action pricing data from the database.
"""
import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.database import get_db_connection


async def clear_action_pricing():
    """Delete all rows from the action_pricing table."""
    conn = None
    try:
        # Get database connection
        conn = await get_db_connection()

        # Count existing records first
        count_result = await conn.fetchval("SELECT COUNT(*) FROM action_pricing")
        print(f"Found {count_result} existing action pricing records")

        if count_result > 0:
            # Delete all records
            await conn.execute("DELETE FROM action_pricing")
            print(f"Successfully deleted all {count_result} records from action_pricing table")
        else:
            print("action_pricing table is already empty")

        # Verify the table is empty
        final_count = await conn.fetchval("SELECT COUNT(*) FROM action_pricing")
        print(f"Verification: action_pricing table now contains {final_count} records")

    except Exception as e:
        print(f"Error clearing action_pricing table: {e}")
        sys.exit(1)
    finally:
        if conn:
            await conn.close()


if __name__ == "__main__":
    asyncio.run(clear_action_pricing())
