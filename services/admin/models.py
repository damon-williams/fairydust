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


# Promotional referral code models
class PromotionalReferralCode(BaseModel):
    id: UUID
    code: str
    description: str
    dust_bonus: int
    max_uses: Optional[int] = None
    current_uses: int = 0
    created_by: UUID
    created_at: datetime
    expires_at: datetime
    is_active: bool


class PromotionalReferralCodeCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=20, description="Promotional code")
    description: str = Field(..., min_length=1, max_length=500, description="Description of the promotion")
    dust_bonus: int = Field(..., ge=1, le=1000, description="DUST bonus for users who redeem this code")
    max_uses: Optional[int] = Field(None, ge=1, le=100000, description="Maximum number of uses (unlimited if None)")
    expires_at: datetime = Field(..., description="When the code expires")


class PromotionalReferralCodeUpdate(BaseModel):
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    dust_bonus: Optional[int] = Field(None, ge=1, le=1000)
    max_uses: Optional[int] = Field(None, ge=1, le=100000)
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class PromotionalReferralCodesResponse(BaseModel):
    codes: list[PromotionalReferralCode]
    total: int
    page: int
    page_size: int
    has_more: bool


class PromotionalReferralRedemption(BaseModel):
    id: UUID
    promotional_code: str
    user_id: UUID
    user_name: str
    dust_bonus: int
    redeemed_at: datetime


class PromotionalReferralRedemptionsResponse(BaseModel):
    redemptions: list[PromotionalReferralRedemption]
    total: int
    page: int
    page_size: int
    has_more: bool