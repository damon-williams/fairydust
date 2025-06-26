# services/ledger/background.py
import asyncio
import json
from datetime import datetime, timedelta

from shared.database import get_db
from shared.redis_client import get_redis

# Global task references
_background_tasks: set[asyncio.Task] = set()
_shutdown_event = asyncio.Event()


async def balance_sync_task():
    """Periodically sync cached balances with database"""
    redis_client = await get_redis()
    db = await get_db()

    while not _shutdown_event.is_set():
        try:
            # Get all cached balance keys
            balance_keys = await redis_client.keys("balance:*")

            for key in balance_keys:
                if _shutdown_event.is_set():
                    break

                user_id = key.split(":")[-1]

                # Get actual balance from database
                result = await db.fetch_one("SELECT dust_balance FROM users WHERE id = $1", user_id)

                if result:
                    # Update cache if exists
                    await redis_client.setex(key, 300, str(result["dust_balance"]))  # 5 minute TTL

            # Sleep for 1 minute
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error in balance sync task: {e}")
            await asyncio.sleep(10)  # Shorter sleep on error


async def expired_transaction_cleanup():
    """Clean up expired pending transactions"""
    db = await get_db()

    while not _shutdown_event.is_set():
        try:
            # Find pending transactions older than 1 hour
            expired_time = datetime.utcnow() - timedelta(hours=1)

            expired_transactions = await db.fetch_all(
                """
                SELECT id, user_id, amount FROM dust_transactions
                WHERE status = 'pending' AND created_at < $1
                """,
                expired_time,
            )

            for tx in expired_transactions:
                # Mark as failed
                await db.execute(
                    """
                    UPDATE dust_transactions
                    SET status = 'failed',
                        updated_at = CURRENT_TIMESTAMP,
                        metadata = jsonb_set(
                            COALESCE(metadata, '{}'),
                            '{failure_reason}',
                            '"Transaction expired"'
                        )
                    WHERE id = $1
                    """,
                    tx["id"],
                )

                # If it was a consume transaction, we might need to refund
                # This depends on business logic

            # Run every 5 minutes
            await asyncio.sleep(300)

        except Exception as e:
            print(f"Error in transaction cleanup task: {e}")
            await asyncio.sleep(30)


async def analytics_aggregation():
    """Aggregate analytics data for faster queries"""
    db = await get_db()

    while not _shutdown_event.is_set():
        try:
            # Aggregate hourly stats
            await db.execute(
                """
                INSERT INTO hourly_app_stats (app_id, hour, unique_users, transactions, dust_consumed)
                SELECT
                    app_id,
                    date_trunc('hour', created_at) as hour,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(*) as transactions,
                    SUM(ABS(amount)) as dust_consumed
                FROM dust_transactions
                WHERE type = 'consume'
                AND created_at >= date_trunc('hour', NOW() - INTERVAL '2 hours')
                AND created_at < date_trunc('hour', NOW() - INTERVAL '1 hour')
                AND app_id IS NOT NULL
                GROUP BY app_id, hour
                ON CONFLICT (app_id, hour) DO UPDATE SET
                    unique_users = EXCLUDED.unique_users,
                    transactions = EXCLUDED.transactions,
                    dust_consumed = EXCLUDED.dust_consumed
                """
            )

            # Run every hour
            await asyncio.sleep(3600)

        except Exception as e:
            print(f"Error in analytics aggregation: {e}")
            await asyncio.sleep(300)


async def balance_update_listener():
    """Listen for balance updates and notify connected clients"""
    redis_client = await get_redis()
    pubsub = redis_client.pubsub()

    # Subscribe to balance update pattern
    await pubsub.psubscribe("balance_update:*")

    try:
        while not _shutdown_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message and message["type"] == "pmessage":
                channel = str(message["channel"])
                data = json.loads(message["data"])

                # In a real implementation, this would notify WebSocket clients
                # For now, just log it
                print(
                    f"Balance update for user {data['user_id']}: {data['old_balance']} -> {data['new_balance']}"
                )

    except Exception as e:
        print(f"Error in balance update listener: {e}")
    finally:
        await pubsub.unsubscribe("balance_update:*")
        await pubsub.close()


async def start_background_tasks():
    """Start all background tasks"""
    global _background_tasks

    # Create tasks
    tasks = [
        asyncio.create_task(balance_sync_task()),
        asyncio.create_task(expired_transaction_cleanup()),
        asyncio.create_task(analytics_aggregation()),
        asyncio.create_task(balance_update_listener()),
    ]

    # Store task references
    _background_tasks = set(tasks)

    # Remove completed tasks
    for task in tasks:
        task.add_done_callback(_background_tasks.discard)


async def stop_background_tasks():
    """Stop all background tasks gracefully"""
    global _background_tasks

    # Signal shutdown
    _shutdown_event.set()

    # Wait for tasks to complete
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)

    # Clear references
    _background_tasks.clear()
    _shutdown_event.clear()
