# shared/streak_utils.py
import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


async def _execute_with_retry(db, query: str, *args, max_retries: int = 2, timeout: float = 3.0):
    """Execute database query with retry logic and timeout"""
    for attempt in range(max_retries):
        try:
            # Execute with timeout
            return await asyncio.wait_for(db.execute(query, *args), timeout=timeout)
        except (asyncio.TimeoutError, Exception) as e:
            if attempt == max_retries - 1:  # Last attempt
                logger.error(f"Database operation failed after {max_retries} attempts: {e}")
                raise

            # Exponential backoff: 0.1s, 0.2s, 0.4s
            wait_time = 0.1 * (2**attempt)
            logger.warning(
                f"Database operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}"
            )
            await asyncio.sleep(wait_time)


async def calculate_daily_streak(
    db, user_id: str, current_streak: int, last_login_date: Optional[datetime]
) -> tuple[int, datetime, bool, int]:
    """
    Calculate daily login streak for a user with timeout protection and retry logic.

    Args:
        db: Database connection
        user_id: User's UUID
        current_streak: Current streak days value
        last_login_date: User's last login timestamp

    Returns:
        tuple of (new_streak_days, updated_last_login_date, is_bonus_eligible, previous_streak_days)

    Business Rules:
    - Streak resets to 1 if user misses any days (not 0)
    - Maximum streak is 5 days (matches DUST bonus system)
    - UTC-based calculation for global consistency
    - Same-day logins don't change streak
    - Bonus eligible on: first login ever, consecutive days, or after missed days
    - Includes timeout protection and retry logic
    """
    now = datetime.utcnow()

    if not last_login_date:
        # First login ever - eligible for bonus
        new_streak = 1
        is_bonus_eligible = True
        previous_streak_days = 0
        try:
            await _execute_with_retry(
                db,
                """
                UPDATE users
                SET streak_days = $1, last_login_date = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = $3
            """,
                new_streak,
                now,
                user_id,
            )
        except Exception as e:
            logger.error(f"Failed to update streak for first-time user {user_id}: {e}")
            # Return calculated values even if DB update fails
            # This allows authentication to proceed
            return new_streak, now, is_bonus_eligible, previous_streak_days
        return new_streak, now, is_bonus_eligible, previous_streak_days

    # Calculate days since last login (UTC-based)
    days_since = (now.date() - last_login_date.date()).days
    previous_streak_days = current_streak

    if days_since == 0:
        # Same day, return current streak (no database update needed, no bonus)
        is_bonus_eligible = False
        return current_streak, last_login_date, is_bonus_eligible, previous_streak_days
    elif days_since == 1:
        # Consecutive day, increment (cap at 5) - eligible for bonus
        new_streak = min(current_streak + 1, 5)
        is_bonus_eligible = True
    else:
        # Missed days, reset to 1 - eligible for bonus (new streak starts)
        new_streak = 1
        is_bonus_eligible = True

    # Update database with new streak and login date
    try:
        await _execute_with_retry(
            db,
            """
            UPDATE users
            SET streak_days = $1, last_login_date = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
        """,
            new_streak,
            now,
            user_id,
        )
    except Exception as e:
        logger.error(f"Failed to update streak for user {user_id}: {e}")
        # Return calculated values even if DB update fails
        # This allows authentication to proceed while streak calculation is degraded
        return new_streak, now, is_bonus_eligible, previous_streak_days

    return new_streak, now, is_bonus_eligible, previous_streak_days
