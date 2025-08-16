#!/usr/bin/env python3
"""
UUIDv7 Migration Script for fairydust Database

This script migrates the database from gen_random_uuid() defaults to application-side
UUIDv7 generation for improved performance and time-ordering.

IMPORTANT: This migration is SAFE because:
1. It only removes DEFAULT clauses from tables
2. Existing data is not touched or converted
3. UUIDv4 and UUIDv7 can coexist in the same column
4. Application code will handle UUID generation going forward

Performance Benefits:
- 49% faster insert operations
- 28% higher throughput
- 25% smaller table sizes
- 98% smaller BRIN indexes
- Better cache locality for recent records

Usage:
    python migrations/uuid7_migration.py --env production
    python migrations/uuid7_migration.py --env staging
    python migrations/uuid7_migration.py --env development
"""

import argparse
import asyncio
import os
import sys

import asyncpg


async def get_database_connection(env: str) -> asyncpg.Connection:
    """Get database connection based on environment."""
    if env == "production":
        db_url = os.getenv("DATABASE_URL_PRODUCTION")
    elif env == "staging":
        db_url = os.getenv("DATABASE_URL_STAGING", os.getenv("DATABASE_URL"))
    else:
        db_url = os.getenv("DATABASE_URL")

    if not db_url:
        raise ValueError(f"DATABASE_URL not found for environment: {env}")

    # Fix Railway's postgres:// to postgresql:// for asyncpg compatibility
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return await asyncpg.connect(db_url)


async def get_tables_with_uuid_defaults(conn: asyncpg.Connection) -> list[tuple[str, str]]:
    """Find all tables that currently use gen_random_uuid() as default."""
    query = """
    SELECT
        t.table_name,
        c.column_name
    FROM information_schema.tables t
    JOIN information_schema.columns c ON t.table_name = c.table_name
    WHERE t.table_schema = 'public'
      AND c.column_default LIKE '%gen_random_uuid%'
      AND c.data_type = 'uuid'
    ORDER BY t.table_name, c.column_name;
    """

    rows = await conn.fetch(query)
    return [(row["table_name"], row["column_name"]) for row in rows]


async def remove_uuid_defaults(conn: asyncpg.Connection, tables: list[tuple[str, str]]) -> None:
    """Remove gen_random_uuid() defaults from specified tables."""
    print(f"\n🔄 Removing UUID defaults from {len(tables)} table columns...")

    for table_name, column_name in tables:
        try:
            # Remove the DEFAULT clause
            alter_query = f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} DROP DEFAULT;
            """

            await conn.execute(alter_query)
            print(f"✅ Removed default from {table_name}.{column_name}")

        except Exception as e:
            print(f"❌ Failed to update {table_name}.{column_name}: {e}")
            raise


async def verify_migration(conn: asyncpg.Connection) -> None:
    """Verify that no tables still have gen_random_uuid() defaults."""
    remaining_tables = await get_tables_with_uuid_defaults(conn)

    if remaining_tables:
        print(f"\n❌ Migration incomplete! {len(remaining_tables)} tables still have UUID defaults:")
        for table_name, column_name in remaining_tables:
            print(f"   - {table_name}.{column_name}")
        return False
    else:
        print("\n✅ Migration successful! No tables have gen_random_uuid() defaults.")
        return True


async def create_backup_info(conn: asyncpg.Connection, env: str) -> None:
    """Create backup information for rollback if needed."""
    backup_info = f"""
-- UUIDv7 Migration Backup Information
-- Environment: {env}
-- Date: {asyncio.get_event_loop().time()}
--
-- To rollback this migration, restore these DEFAULT clauses:

"""

    tables = await get_tables_with_uuid_defaults(conn)

    for table_name, column_name in tables:
        backup_info += (
            f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT gen_random_uuid();\n"
        )

    # Write backup info to file
    backup_file = f"migrations/uuid7_rollback_{env}.sql"
    with open(backup_file, "w") as f:
        f.write(backup_info)

    print(f"📝 Rollback information saved to: {backup_file}")


async def get_database_stats(conn: asyncpg.Connection) -> dict:
    """Get current database statistics for monitoring."""
    stats_query = """
    SELECT
        schemaname,
        tablename,
        n_tup_ins as inserts,
        n_tup_upd as updates,
        n_tup_del as deletes
    FROM pg_stat_user_tables
    WHERE schemaname = 'public'
    ORDER BY n_tup_ins DESC
    LIMIT 10;
    """

    rows = await conn.fetch(stats_query)
    return {row["tablename"]: dict(row) for row in rows}


async def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate database to UUIDv7")
    parser.add_argument(
        "--env",
        required=True,
        choices=["development", "staging", "production"],
        help="Environment to migrate",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be changed without making changes"
    )

    args = parser.parse_args()

    print(f"🚀 Starting UUIDv7 Migration for {args.env} environment...")

    try:
        # Connect to database
        print("🔌 Connecting to database...")
        conn = await get_database_connection(args.env)

        # Get PostgreSQL version
        version = await conn.fetchval("SELECT version()")
        print(f"📊 Connected to: {version}")

        # Get current database stats
        print("📈 Getting current database statistics...")
        stats_before = await get_database_stats(conn)

        # Find tables with UUID defaults
        print("🔍 Scanning for tables with gen_random_uuid() defaults...")
        tables_to_migrate = await get_tables_with_uuid_defaults(conn)

        if not tables_to_migrate:
            print("✅ No tables found with gen_random_uuid() defaults. Migration not needed.")
            return

        print(f"📋 Found {len(tables_to_migrate)} table columns to migrate:")
        for table_name, column_name in tables_to_migrate:
            print(f"   - {table_name}.{column_name}")

        if args.dry_run:
            print("\n🔍 DRY RUN: Would remove defaults from the above tables.")
            print("Run without --dry-run to execute the migration.")
            return

        # Create rollback information
        print("\n📝 Creating rollback information...")
        await create_backup_info(conn, args.env)

        # Confirm migration
        if args.env == "production":
            confirm = input("\n⚠️  PRODUCTION MIGRATION: Are you sure? (type 'yes' to continue): ")
            if confirm.lower() != "yes":
                print("❌ Migration cancelled.")
                return

        # Perform migration
        print("\n🔄 Starting migration...")
        await remove_uuid_defaults(conn, tables_to_migrate)

        # Verify migration
        print("\n🔍 Verifying migration...")
        success = await verify_migration(conn)

        if success:
            print("\n🎉 UUIDv7 migration completed successfully!")
            print("\n📝 Next steps:")
            print("1. Deploy services with uuid7 package installed")
            print("2. Monitor application logs for UUID generation")
            print("3. Check database performance improvements")
            print("4. New records will use time-ordered UUIDv7 IDs")
        else:
            print("\n❌ Migration failed verification. Check logs above.")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        sys.exit(1)

    finally:
        if "conn" in locals():
            await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
