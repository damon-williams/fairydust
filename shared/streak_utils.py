# shared/streak_utils.py
from datetime import datetime
from typing import Optional

async def calculate_daily_streak(
    db,
    user_id: str,
    current_streak: int,
    last_login_date: Optional[datetime]
) -> tuple[int, datetime]:
    """
    Calculate daily login streak for a user.
    
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
    """
    now = datetime.utcnow()
    
    if not last_login_date:
        # First login ever
        new_streak = 1
        await db.execute("""
            UPDATE users 
            SET streak_days = $1, last_login_date = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
        """, new_streak, now, user_id)
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
    await db.execute("""
        UPDATE users 
        SET streak_days = $1, last_login_date = $2, updated_at = CURRENT_TIMESTAMP
        WHERE id = $3
    """, new_streak, now, user_id)
    
    return new_streak, now