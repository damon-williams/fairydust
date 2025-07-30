# shared/daily_bonus_utils.py
import asyncio
import logging
from datetime import datetime
from typing import Optional

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
        last_login_date: User's last login timestamp

    Returns:
        tuple of (is_bonus_eligible, current_time)

    Business Rules:
    - Eligible if: first login ever OR different UTC date from last login
    - Uses UTC dates for consistency
    - Simple and predictable
    """
    now = datetime.utcnow()

    if not last_login_date:
        # First login ever - eligible for bonus
        return True, now

    # Check if different UTC dates
    last_login_date_only = last_login_date.date()
    current_date = now.date()
    is_different_date = current_date != last_login_date_only

    return is_different_date, now


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
        SET last_login_date = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        current_time,
        user_id,
    )

    # Last login date updated successfully
    return current_time
