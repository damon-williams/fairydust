# shared/streak_utils.py
from datetime import datetime
from typing import Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

async def _execute_with_retry(db, query: str, *args, max_retries: int = 3, timeout: float = 10.0):
    """Execute database query with retry logic and timeout"""
    for attempt in range(max_retries):
        try:
            # Execute with timeout
            return await asyncio.wait_for(
                db.execute(query, *args),
                timeout=timeout
            )
        except (asyncio.TimeoutError, Exception) as e:
            if attempt == max_retries - 1:  # Last attempt
                logger.error(f"Database operation failed after {max_retries} attempts: {e}")
                raise
            
            # Exponential backoff: 0.1s, 0.2s, 0.4s
            wait_time = 0.1 * (2 ** attempt)
            logger.warning(f"Database operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
            await asyncio.sleep(wait_time)

async def calculate_daily_streak(
    db,
    user_id: str,
    current_streak: int,
    last_login_date: Optional[datetime]
) -> tuple[int, datetime]:
    """
    Calculate daily login streak for a user with timeout protection and retry logic.
    
    Args:
        db: Database connection
        user_id: User's UUID
        current_streak: Current streak days value
        last_login_date: User's last login timestamp
    
    Returns:
        tuple of (new_streak_days, updated_last_login_date)
    
    Business Rules:
    - Streak resets to 1 if user misses any days (not 0)
    - Maximum streak is 5 days (matches DUST bonus system)
    - UTC-based calculation for global consistency
    - Same-day logins don't change streak
    - Includes timeout protection and retry logic
    """
    now = datetime.utcnow()
    
    if not last_login_date:
        # First login ever
        new_streak = 1
        try:
            await _execute_with_retry(db, """
                UPDATE users 
                SET streak_days = $1, last_login_date = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = $3
            """, new_streak, now, user_id)
        except Exception as e:
            logger.error(f"Failed to update streak for first-time user {user_id}: {e}")
            # Return calculated values even if DB update fails
            # This allows authentication to proceed
            return new_streak, now
        return new_streak, now
    
    # Calculate days since last login (UTC-based)
    days_since = (now.date() - last_login_date.date()).days
    
    if days_since == 0:
        # Same day, return current streak (no database update needed)
        return current_streak, last_login_date
    elif days_since == 1:
        # Consecutive day, increment (cap at 5)
        new_streak = min(current_streak + 1, 5)
    else:
        # Missed days, reset to 1
        new_streak = 1
    
    # Update database with new streak and login date
    try:
        await _execute_with_retry(db, """
            UPDATE users 
            SET streak_days = $1, last_login_date = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
        """, new_streak, now, user_id)
    except Exception as e:
        logger.error(f"Failed to update streak for user {user_id}: {e}")
        # Return calculated values even if DB update fails
        # This allows authentication to proceed while streak calculation is degraded
        return new_streak, now
    
    return new_streak, now