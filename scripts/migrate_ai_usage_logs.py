#!/usr/bin/env python3
"""
Migration script to create ai_usage_logs table for unified AI model tracking.
Run this script to create the new table structure for image and video usage logging.

Usage:
    DATABASE_URL=your_database_url python scripts/migrate_ai_usage_logs.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.database import Database


async def run_migration():
    """Run the AI usage logs migration"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("Example: DATABASE_URL=postgresql://user:pass@host:port/dbname python scripts/migrate_ai_usage_logs.py")
        return False

    # Set the DATABASE_URL for the shared database module
    import os
    os.environ["DATABASE_URL"] = database_url
    
    try:
        # Initialize the database connection pool
        from shared.database import init_db, get_db
        await init_db()
        db = await get_db()
        print("✅ Connected to database")
        
        # Read the migration SQL
        migration_file = project_root / "migrations" / "create_ai_usage_logs.sql"
        if not migration_file.exists():
            print(f"❌ Migration file not found: {migration_file}")
            return False
            
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print("🔄 Running AI usage logs migration...")
        
        # Check if table already exists
        table_exists = await db.fetch_one(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ai_usage_logs')"
        )
        
        if table_exists["exists"]:
            print("✓ ai_usage_logs table already exists, skipping migration")
            return True
        
        # Execute the migration using the schema method
        await db.execute_schema(migration_sql)
        
        print("✅ Migration completed successfully!")
        print("📊 Created ai_usage_logs table for unified AI model tracking")
        print("🔍 Created unified_ai_usage view for backward compatibility")
        print("📈 Ready to track text, image, and video model usage")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
        
    finally:
        # Close the database connection pool
        from shared.database import close_db
        await close_db()


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)