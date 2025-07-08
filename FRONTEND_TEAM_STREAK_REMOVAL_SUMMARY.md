# Frontend Team: Streak System → Daily Login Bonus Migration

## Summary
We've removed the complex streak system and replaced it with a simple daily login bonus. This eliminates timezone issues and simplifies the user experience.

## ⚠️ BREAKING CHANGES

### 1. API Response Changes

#### Authentication Endpoints (`POST /auth/otp/verify`, `POST /auth/oauth/{provider}`)
**REMOVED:**
```json
{
  "streak_bonus_eligible": boolean,
  "current_streak_day": number
}
```

**ADDED:**
```json
{
  "daily_bonus_eligible": boolean
}
```

#### User Profile Endpoint (`GET /users/me`)
**REMOVED:**
```json
{
  "streak_days": number,
  "is_streak_bonus_eligible": boolean,
  "current_streak_day": number
}
```

**ADDED:**
```json
{
  "is_daily_bonus_eligible": boolean
}
```

### 2. Endpoint Changes

#### DUST Grant Endpoint
**OLD:** `POST /grants/app-streak`
```json
{
  "user_id": "uuid",
  "app_id": "string",
  "amount": number,
  "streak_days": number,
  "idempotency_key": "string"
}
```

**NEW:** `POST /grants/daily-bonus`
```json
{
  "user_id": "uuid", 
  "app_id": "string",
  "idempotency_key": "string"
}
```
*Note: Amount is now configured in admin portal, not sent by frontend*

## ✅ Required Frontend Changes

### 1. Update Auth Flow Logic
```javascript
// OLD
if (authResponse.streak_bonus_eligible && authResponse.current_streak_day) {
  showStreakBonus(authResponse.current_streak_day);
}

// NEW  
if (authResponse.daily_bonus_eligible) {
  showDailyBonus(); // No day number needed
}
```

### 2. Update User Profile Logic
```javascript
// OLD
if (user.is_streak_bonus_eligible) {
  showStreakIndicator(user.current_streak_day, user.streak_days);
}

// NEW
if (user.is_daily_bonus_eligible) {
  showDailyBonusIndicator(); // Much simpler!
}
```

### 3. Update Bonus Claiming Logic
```javascript
// OLD
const claimStreakBonus = async (streakDay) => {
  const amount = getStreakDayAmount(streakDay); // Complex calculation
  return fetch('/grants/app-streak', {
    method: 'POST',
    body: JSON.stringify({
      user_id,
      app_id,
      amount,
      streak_days: streakDay,
      idempotency_key
    })
  });
};

// NEW
const claimDailyBonus = async () => {
  return fetch('/grants/daily-bonus', {
    method: 'POST', 
    body: JSON.stringify({
      user_id,
      app_id,
      idempotency_key
    })
  });
  // Amount is automatically determined by backend config
};
```

### 4. Remove Streak-Related UI Components
- Remove streak day indicators (1/5, 2/5, etc.)
- Remove streak counter displays
- Remove streak explanation modals/tooltips
- Simplify bonus UI to just "Daily Login Bonus Available"

### 5. Update State Management
```javascript
// Remove from user state:
// - streak_days
// - current_streak_day  
// - streak_bonus_eligible

// Add to user state:
// - is_daily_bonus_eligible (boolean)
```

## 💰 Benefits for Users

1. **No More Broken Streaks**: Users can't lose progress due to timezone confusion
2. **Predictable Bonuses**: Same bonus amount every day (configurable by admin)
3. **Simpler UX**: Just "claim daily bonus" instead of complex streak tracking
4. **Fair for All Timezones**: Works consistently regardless of user location

## 🔧 Admin Configuration

The daily bonus amount is now configurable in the admin portal via the `system_config` table:
- Key: `daily_login_bonus_amount`
- Default: `5` DUST
- Admin can change this value without code deployments

## 🎯 Testing Checklist

- [ ] Auth flow shows `daily_bonus_eligible` instead of streak fields
- [ ] `/users/me` returns `is_daily_bonus_eligible` field
- [ ] Daily bonus claiming works with new endpoint
- [ ] Bonus claiming prevents duplicate claims for same day
- [ ] UI no longer shows streak counters or day indicators
- [ ] Error handling updated for new API responses

## ❓ Questions?

The new system is much simpler! If you have any questions about the migration, please reach out. The key principle is: **one daily bonus per day, regardless of streaks or timing**.