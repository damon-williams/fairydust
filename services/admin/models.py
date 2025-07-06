# services/admin/models.py
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Referral configuration models
class MilestoneReward(BaseModel):
    referral_count: int = Field(..., ge=1, le=1000)
    bonus_amount: int = Field(..., ge=1, le=1000)


class ReferralConfig(BaseModel):
    referee_bonus: int = Field(..., ge=1, le=100, description="DUST bonus for new users")
    referrer_bonus: int = Field(..., ge=1, le=100, description="DUST bonus for referring users")
    milestone_rewards: list[MilestoneReward] = Field(default_factory=list)
    code_expiry_days: int = Field(..., ge=1, le=365, description="Days until referral codes expire")
    max_referrals_per_user: int = Field(..., ge=1, le=10000, description="Maximum referrals per user")
    system_enabled: bool = Field(True, description="Whether referral system is enabled")


class ReferralConfigUpdate(BaseModel):
    referee_bonus: Optional[int] = Field(None, ge=1, le=100)
    referrer_bonus: Optional[int] = Field(None, ge=1, le=100)
    milestone_rewards: Optional[list[MilestoneReward]] = None
    code_expiry_days: Optional[int] = Field(None, ge=1, le=365)
    max_referrals_per_user: Optional[int] = Field(None, ge=1, le=10000)
    system_enabled: Optional[bool] = None


# Referral statistics models
class TopReferrer(BaseModel):
    user_id: UUID
    fairyname: str
    successful_referrals: int
    total_dust_earned: int


class DailyStat(BaseModel):
    date: str  # YYYY-MM-DD format
    codes_created: int
    successful_referrals: int
    dust_granted: int


class ReferralSystemStats(BaseModel):
    total_codes_created: int
    total_successful_referrals: int
    conversion_rate: float
    total_dust_granted: int
    top_referrers: list[TopReferrer]
    daily_stats: list[DailyStat]


class ReferralCodeDisplay(BaseModel):
    referral_code: str
    user_id: UUID
    user_name: str
    created_at: datetime
    status: str  # "active", "expired", "inactive"
    successful_referrals: int


class ReferralCodesResponse(BaseModel):
    codes: list[ReferralCodeDisplay]
    total: int
    page: int
    page_size: int
    has_more: bool


class ReferralRedemptionDisplay(BaseModel):
    referral_code: str
    referrer_name: str
    referee_name: str
    redeemed_at: datetime
    referee_bonus: int
    referrer_bonus: int


class ReferralRedemptionsResponse(BaseModel):
    redemptions: list[ReferralRedemptionDisplay]
    total: int
    page: int
    page_size: int
    has_more: bool