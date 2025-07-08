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


async def calculate_daily_streak_for_auth(
    db, user_id: str, current_streak: int, last_login_date: Optional[datetime]
) -> tuple[int, datetime, bool, int]:
    """
    Calculate daily login streak for auth response WITHOUT updating database.
    Database updates are handled by the DUST grant endpoint.

    Args:
        db: Database connection
        user_id: User's UUID
        current_streak: Current streak days value
        last_login_date: User's last login timestamp

    Returns:
        tuple of (calculated_streak_days, current_time, is_bonus_eligible, current_streak_day)

    Business Rules:
    - Streak continues indefinitely with 5-day reward cycle
    - current_streak_day = ((total_streak_days - 1) % 5) + 1
    - Streak resets to 1 if user misses any days
    - UTC-based calculation for global consistency
    - Same-day logins don't change streak
    - Bonus eligible on: first login ever, consecutive days, or after missed days
    - NO DATABASE UPDATES - read-only calculation for auth response
    """
    now = datetime.utcnow()
    
    print(f"🔍 STREAK_DEBUG [{user_id}]: === Calculating Streak ===", flush=True)
    print(f"🕐 STREAK_DEBUG [{user_id}]: Current UTC time: {now.isoformat()}", flush=True)
    print(f"🕐 STREAK_DEBUG [{user_id}]: Current UTC date: {now.date()}", flush=True)
    print(f"📊 STREAK_DEBUG [{user_id}]: Current streak: {current_streak} days", flush=True)
    print(f"📅 STREAK_DEBUG [{user_id}]: Last login: {last_login_date.isoformat() if last_login_date else 'NEVER'}", flush=True)

    if not last_login_date:
        # First login ever - eligible for bonus
        new_streak = 1
        is_bonus_eligible = True
        current_streak_day = 1
        print(f"🎉 STREAK_DEBUG [{user_id}]: FIRST LOGIN EVER - Bonus eligible!", flush=True)
        print(f"✅ STREAK_DEBUG [{user_id}]: New streak: 1, Bonus: YES, Streak day: 1", flush=True)
        # NO DATABASE UPDATE - return calculated values only
        return new_streak, now, is_bonus_eligible, current_streak_day

    # Calculate days since last login (UTC-based)
    last_login_date_only = last_login_date.date() if last_login_date else None
    days_since = (now.date() - last_login_date.date()).days
    
    print(f"📅 STREAK_DEBUG [{user_id}]: Last login date only: {last_login_date_only}", flush=True)
    print(f"📏 STREAK_DEBUG [{user_id}]: Days since last login: {days_since}", flush=True)
    
    # Human-readable interpretation
    if days_since == 0:
        print(f"🔄 STREAK_DEBUG [{user_id}]: SAME DAY LOGIN - No bonus", flush=True)
    elif days_since == 1:
        print(f"🔥 STREAK_DEBUG [{user_id}]: CONSECUTIVE DAY - Streak continues!", flush=True)
    else:
        print(f"💔 STREAK_DEBUG [{user_id}]: MISSED {days_since-1} DAYS - Streak broken!", flush=True)

    if days_since == 0:
        # Same day, return current streak (no bonus)
        is_bonus_eligible = False
        current_streak_day = ((current_streak - 1) % 5) + 1
        print(f"❌ STREAK_DEBUG [{user_id}]: No change - Same day login", flush=True)
        print(f"📊 STREAK_DEBUG [{user_id}]: Keeping streak: {current_streak}, Bonus: NO, Streak day: {current_streak_day}", flush=True)
        return current_streak, last_login_date, is_bonus_eligible, current_streak_day
    elif days_since == 1:
        # Consecutive day, increment (no cap - infinite streak) - eligible for bonus
        new_streak = current_streak + 1
        is_bonus_eligible = True
        print(f"➕ STREAK_DEBUG [{user_id}]: Incrementing streak from {current_streak} to {new_streak}", flush=True)
    else:
        # Missed days, reset to 1 - eligible for bonus (new streak starts)
        new_streak = 1
        is_bonus_eligible = True
        print(f"🔄 STREAK_DEBUG [{user_id}]: Resetting streak to 1 (was {current_streak})", flush=True)

    # Calculate current streak day in 5-day cycle
    current_streak_day = ((new_streak - 1) % 5) + 1
    
    print(f"🎯 STREAK_DEBUG [{user_id}]: Streak day in cycle: {current_streak_day} (of 5)", flush=True)
    print(f"✅ STREAK_DEBUG [{user_id}]: Final result - Streak: {new_streak}, Bonus: {'YES' if is_bonus_eligible else 'NO'}, Streak day: {current_streak_day}", flush=True)
    print(f"🔍 STREAK_DEBUG [{user_id}]: === End Streak Calculation ===", flush=True)

    # NO DATABASE UPDATE - return calculated values only
    return new_streak, now, is_bonus_eligible, current_streak_day


async def update_daily_streak_for_grant(
    db, user_id: str, current_streak: int, last_login_date: Optional[datetime]
) -> tuple[int, datetime]:
    """
    Update daily login streak when processing DUST grant.
    This function DOES update the database.

    Args:
        db: Database connection
        user_id: User's UUID
        current_streak: Current streak days value
        last_login_date: User's last login timestamp

    Returns:
        tuple of (new_streak_days, updated_last_login_date)
        
    Business Rules:
    - Streak continues indefinitely (no cap at 5)
    - Streak resets to 1 if user misses any days
    - Updates database with new values
    """
    now = datetime.utcnow()
    
    print(f"🔄 STREAK_UPDATE_DEBUG [{user_id}]: === Updating Streak in DB ===", flush=True)
    print(f"🕐 STREAK_UPDATE_DEBUG [{user_id}]: Current UTC time: {now.isoformat()}", flush=True)
    print(f"📊 STREAK_UPDATE_DEBUG [{user_id}]: Current streak: {current_streak} days", flush=True)
    print(f"📅 STREAK_UPDATE_DEBUG [{user_id}]: Last login: {last_login_date.isoformat() if last_login_date else 'NEVER'}", flush=True)

    if not last_login_date:
        # First login ever
        new_streak = 1
        print(f"🎉 STREAK_UPDATE_DEBUG [{user_id}]: First login - Setting streak to 1", flush=True)
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
        print(f"✅ STREAK_UPDATE_DEBUG [{user_id}]: Database updated - Streak: 1, Last login: {now.isoformat()}", flush=True)
        return new_streak, now

    # Calculate days since last login (UTC-based)
    days_since = (now.date() - last_login_date.date()).days
    print(f"📏 STREAK_UPDATE_DEBUG [{user_id}]: Days since last login: {days_since}", flush=True)

    if days_since == 0:
        # Same day, no update needed
        print(f"🔄 STREAK_UPDATE_DEBUG [{user_id}]: Same day - No database update needed", flush=True)
        return current_streak, last_login_date
    elif days_since == 1:
        # Consecutive day, increment (no cap - infinite streak)
        new_streak = current_streak + 1
        print(f"🔥 STREAK_UPDATE_DEBUG [{user_id}]: Consecutive day - Incrementing to {new_streak}", flush=True)
    else:
        # Missed days, reset to 1
        new_streak = 1
        print(f"💔 STREAK_UPDATE_DEBUG [{user_id}]: Missed {days_since-1} days - Resetting to 1", flush=True)

    # Update database with new streak and login date
    print(f"💾 STREAK_UPDATE_DEBUG [{user_id}]: Updating database...", flush=True)
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
    
    print(f"✅ STREAK_UPDATE_DEBUG [{user_id}]: Database updated - Streak: {new_streak}, Last login: {now.isoformat()}", flush=True)
    print(f"🔄 STREAK_UPDATE_DEBUG [{user_id}]: === End Streak Update ===", flush=True)

    return new_streak, now
