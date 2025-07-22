-- Quick solution: Use grace period for streak calculations
-- This allows users in different timezones to maintain streaks

-- Instead of strict 24-hour periods, we use:
-- - Less than 24 hours: Same day (no bonus)
-- - 24-36 hours: Consecutive day (streak continues, bonus eligible)
-- - More than 36 hours: Streak broken (reset to 1)

-- This gives users a 12-hour buffer on each side of their timezone
-- to account for logging in at different times of day