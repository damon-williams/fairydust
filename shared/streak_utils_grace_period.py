# shared/streak_utils.py with grace period for timezone differences
import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Grace period in hours to account for timezone differences
# 36 hours allows for all timezones to have "consecutive day" logins
STREAK_GRACE_PERIOD_HOURS = 36


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
    Calculate daily login streak with grace period for timezone differences.

    Uses a 36-hour grace period instead of strict 24-hour periods to allow
    users in different timezones to maintain streaks when logging in on
    consecutive calendar days in their local time.
    """
    now = datetime.utcnow()

    print(f"🔍 STREAK_DEBUG [{user_id}]: === Calculating Streak (With Grace Period) ===", flush=True)
    print(f"🕐 STREAK_DEBUG [{user_id}]: Current UTC time: {now.isoformat()}", flush=True)
    print(f"🕐 STREAK_DEBUG [{user_id}]: Current UTC date: {now.date()}", flush=True)
    print(
        f"⏰ STREAK_DEBUG [{user_id}]: Grace period: {STREAK_GRACE_PERIOD_HOURS} hours", flush=True
    )
    print(f"📊 STREAK_DEBUG [{user_id}]: Current streak: {current_streak} days", flush=True)
    print(
        f"📅 STREAK_DEBUG [{user_id}]: Last login: {last_login_date.isoformat() if last_login_date else 'NEVER'}",
        flush=True,
    )

    if not last_login_date:
        # First login ever - eligible for bonus
        new_streak = 1
        is_bonus_eligible = True
        current_streak_day = 1
        print(f"🎉 STREAK_DEBUG [{user_id}]: FIRST LOGIN EVER - Bonus eligible!", flush=True)
        print(f"✅ STREAK_DEBUG [{user_id}]: New streak: 1, Bonus: YES, Streak day: 1", flush=True)
        return new_streak, now, is_bonus_eligible, current_streak_day

    # Calculate hours since last login
    time_since = now - last_login_date
    hours_since = time_since.total_seconds() / 3600
    days_since = (now.date() - last_login_date.date()).days

    print(f"📅 STREAK_DEBUG [{user_id}]: Last login date only: {last_login_date.date()}", flush=True)
    print(f"⏱️ STREAK_DEBUG [{user_id}]: Hours since last login: {hours_since:.1f}", flush=True)
    print(f"📏 STREAK_DEBUG [{user_id}]: Calendar days since: {days_since}", flush=True)

    # Determine streak status with grace period
    if hours_since < 24:
        # Less than 24 hours - same day login
        print(f"🔄 STREAK_DEBUG [{user_id}]: SAME DAY LOGIN (< 24 hours) - No bonus", flush=True)
        is_bonus_eligible = False
        current_streak_day = ((current_streak - 1) % 5) + 1
        return current_streak, last_login_date, is_bonus_eligible, current_streak_day
    elif hours_since <= STREAK_GRACE_PERIOD_HOURS:
        # Within grace period - streak continues
        print(f"🔥 STREAK_DEBUG [{user_id}]: WITHIN GRACE PERIOD - Streak continues!", flush=True)
        new_streak = current_streak + 1
        is_bonus_eligible = True
    else:
        # Beyond grace period - streak resets
        print(
            f"💔 STREAK_DEBUG [{user_id}]: BEYOND GRACE PERIOD ({hours_since:.1f} > {STREAK_GRACE_PERIOD_HOURS} hours) - Streak broken!",
            flush=True,
        )
        new_streak = 1
        is_bonus_eligible = True

    # Calculate current streak day in 5-day cycle
    current_streak_day = ((new_streak - 1) % 5) + 1

    print(
        f"🎯 STREAK_DEBUG [{user_id}]: Streak day in cycle: {current_streak_day} (of 5)", flush=True
    )
    print(
        f"✅ STREAK_DEBUG [{user_id}]: Final result - Streak: {new_streak}, Bonus: {'YES' if is_bonus_eligible else 'NO'}, Streak day: {current_streak_day}",
        flush=True,
    )
    print(f"🔍 STREAK_DEBUG [{user_id}]: === End Streak Calculation ===", flush=True)

    return new_streak, now, is_bonus_eligible, current_streak_day


async def update_daily_streak_for_grant(
    db, user_id: str, current_streak: int, last_login_date: Optional[datetime]
) -> tuple[int, datetime]:
    """
    Update daily login streak when processing DUST grant.
    This function DOES update the database.
    Uses same grace period logic as calculate function.
    """
    now = datetime.utcnow()

    print(f"🔄 STREAK_UPDATE_DEBUG [{user_id}]: === Updating Streak in DB ===", flush=True)
    print(f"🕐 STREAK_UPDATE_DEBUG [{user_id}]: Current UTC time: {now.isoformat()}", flush=True)
    print(f"📊 STREAK_UPDATE_DEBUG [{user_id}]: Current streak: {current_streak} days", flush=True)
    print(
        f"📅 STREAK_UPDATE_DEBUG [{user_id}]: Last login: {last_login_date.isoformat() if last_login_date else 'NEVER'}",
        flush=True,
    )

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
        print(
            f"✅ STREAK_UPDATE_DEBUG [{user_id}]: Database updated - Streak: 1, Last login: {now.isoformat()}",
            flush=True,
        )
        return new_streak, now

    # Calculate hours since last login
    time_since = now - last_login_date
    hours_since = time_since.total_seconds() / 3600

    print(
        f"⏱️ STREAK_UPDATE_DEBUG [{user_id}]: Hours since last login: {hours_since:.1f}", flush=True
    )

    if hours_since < 24:
        # Same day, no update needed
        print(
            f"🔄 STREAK_UPDATE_DEBUG [{user_id}]: Same day - No database update needed", flush=True
        )
        return current_streak, last_login_date
    elif hours_since <= STREAK_GRACE_PERIOD_HOURS:
        # Within grace period - increment
        new_streak = current_streak + 1
        print(
            f"🔥 STREAK_UPDATE_DEBUG [{user_id}]: Within grace period - Incrementing to {new_streak}",
            flush=True,
        )
    else:
        # Beyond grace period - reset
        new_streak = 1
        print(
            f"💔 STREAK_UPDATE_DEBUG [{user_id}]: Beyond grace period - Resetting to 1", flush=True
        )

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

    print(
        f"✅ STREAK_UPDATE_DEBUG [{user_id}]: Database updated - Streak: {new_streak}, Last login: {now.isoformat()}",
        flush=True,
    )
    print(f"🔄 STREAK_UPDATE_DEBUG [{user_id}]: === End Streak Update ===", flush=True)

    return new_streak, now
