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

    print(f"🔍 DAILY_BONUS_DEBUG [{user_id}]: === Checking Daily Bonus Eligibility ===", flush=True)
    print(f"🕐 DAILY_BONUS_DEBUG [{user_id}]: Current UTC time: {now.isoformat()}", flush=True)
    print(f"📅 DAILY_BONUS_DEBUG [{user_id}]: Current UTC date: {now.date()}", flush=True)
    print(
        f"📅 DAILY_BONUS_DEBUG [{user_id}]: Last login: {last_login_date.isoformat() if last_login_date else 'NEVER'}",
        flush=True,
    )

    if not last_login_date:
        # First login ever - eligible for bonus
        print(f"🎉 DAILY_BONUS_DEBUG [{user_id}]: FIRST LOGIN EVER - Bonus eligible!", flush=True)
        return True, now

    # Check if different UTC dates
    last_login_date_only = last_login_date.date()
    current_date = now.date()

    print(f"📅 DAILY_BONUS_DEBUG [{user_id}]: Last login date: {last_login_date_only}", flush=True)
    print(f"📅 DAILY_BONUS_DEBUG [{user_id}]: Current date: {current_date}", flush=True)

    is_different_date = current_date != last_login_date_only

    if is_different_date:
        print(f"🎉 DAILY_BONUS_DEBUG [{user_id}]: DIFFERENT DATE - Bonus eligible!", flush=True)
    else:
        print(f"🔄 DAILY_BONUS_DEBUG [{user_id}]: SAME DATE - No bonus", flush=True)

    print(f"✅ DAILY_BONUS_DEBUG [{user_id}]: Bonus eligible: {is_different_date}", flush=True)
    print(f"🔍 DAILY_BONUS_DEBUG [{user_id}]: === End Daily Bonus Check ===", flush=True)

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
    print(
        f"💾 DAILY_BONUS_UPDATE [{user_id}]: Updating last login date to {current_time.isoformat()}",
        flush=True,
    )

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

    print(f"✅ DAILY_BONUS_UPDATE [{user_id}]: Last login date updated", flush=True)
    return current_time
