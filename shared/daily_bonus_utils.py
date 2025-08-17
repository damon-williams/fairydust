# shared/daily_bonus_utils.py
import asyncio
import logging
from datetime import datetime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)


async def _execute_with_retry(db, query: str, *args, max_retries: int = 2, timeout: float = 3.0):
    """Execute database query with retry logic and timeout"""
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(db.execute(query, *args), timeout=timeout)
        except (asyncio.TimeoutError, Exception) as e:
            if attempt == max_retries - 1:
                logger.error(f"Database operation failed after {max_retries} attempts: {e}")
                raise

            wait_time = 0.1 * (2**attempt)
            logger.warning(
                f"Database operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}"
            )
            await asyncio.sleep(wait_time)


async def check_daily_bonus_eligibility(
    db, user_id: str, last_login_date: Optional[datetime]
) -> tuple[bool, datetime]:
    """
    Check if user is eligible for daily login bonus.

    Args:
        db: Database connection
        user_id: User's UUID
        last_login_date: User's last login timestamp (stored in UTC)

    Returns:
        tuple of (is_bonus_eligible, current_time_utc)

    Business Rules:
    - Eligible if: first login ever OR different calendar date in US Pacific Time
    - Daily reset happens at midnight Pacific Time (PT/PDT)
    - This means: midnight PT, 3 AM ET, 8 AM UTC (winter) or 7 AM UTC (summer)
    """
    # Get current time in UTC (for database storage)
    now_utc = datetime.utcnow()

    # Define Pacific timezone
    pacific_tz = pytz.timezone("America/Los_Angeles")

    # Convert current UTC time to Pacific for comparison
    now_utc_aware = pytz.UTC.localize(now_utc)
    now_pacific = now_utc_aware.astimezone(pacific_tz)

    if not last_login_date:
        # First login ever - eligible for bonus
        logger.info(f"🎁 DAILY_BONUS: User {user_id} first login - eligible for bonus")
        return True, now_utc

    # Convert last login from UTC to Pacific for date comparison
    if last_login_date.tzinfo is None:
        # Add UTC timezone info if missing
        last_login_date = pytz.UTC.localize(last_login_date)
    last_login_pacific = last_login_date.astimezone(pacific_tz)

    # Check if different calendar dates in Pacific Time
    last_login_date_only = last_login_pacific.date()
    current_date_pacific = now_pacific.date()
    is_different_date = current_date_pacific != last_login_date_only

    logger.info(
        f"🎁 DAILY_BONUS: User {user_id} - "
        f"Last login: {last_login_date_only} PT, "
        f"Current: {current_date_pacific} PT, "
        f"Eligible: {is_different_date}"
    )

    return is_different_date, now_utc


async def update_last_login_for_bonus(db, user_id: str, current_time: datetime) -> datetime:
    """
    Update user's last login date when claiming daily bonus.

    Args:
        db: Database connection
        user_id: User's UUID
        current_time: Current timestamp to set

    Returns:
        Updated last login timestamp
    """
    # Update last login date for daily bonus tracking

    await _execute_with_retry(
        db,
        """
        UPDATE users
        SET last_login_date = $1, total_logins = total_logins + 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        current_time,
        user_id,
    )

    # Last login date updated successfully
    return current_time
