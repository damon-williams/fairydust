import re
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# Auth models
# Auth models
class OTPRequest(BaseModel):
    identifier: str  # Email or phone number
    identifier_type: Literal["email", "phone"]

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v, info):
        # Get identifier_type from the data being validated
        if hasattr(info, "data") and info.data.get("identifier_type") == "email":
            # Basic email validation
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
                raise ValueError("Invalid email format")
        elif hasattr(info, "data") and info.data.get("identifier_type") == "phone":
            # Basic phone validation (E.164 format)
            if not re.match(r"^\+[1-9]\d{1,14}$", v):
                raise ValueError("Phone must be in E.164 format (e.g., +1234567890)")
        return v


class OTPVerify(BaseModel):
    identifier: str
    code: str = Field(..., min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v):
        if not v.isdigit():
            raise ValueError("OTP code must contain only digits")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class OAuthCallback(BaseModel):
    provider: Literal["google", "apple", "facebook"]
    code: str
    state: Optional[str] = None


# User models
class UserCreate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    fairyname: Optional[str] = None
    auth_provider: str
    provider_id: str


class UserUpdate(BaseModel):
    fairyname: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    first_name: Optional[str] = Field(None, max_length=100)
    birth_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_onboarding_completed: Optional[bool] = None


class User(BaseModel):
    id: UUID
    fairyname: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_admin: bool = False
    first_name: Optional[str] = None
    birth_date: Optional[date] = None
    is_onboarding_completed: bool = False
    last_login_date: Optional[datetime] = None
    auth_provider: Optional[str] = None
    avatar_url: Optional[str] = None
    avatar_uploaded_at: Optional[datetime] = None
    avatar_size_bytes: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    dust_balance: int = 0  # Denormalized for performance
    # Calculated daily bonus fields (not stored in database)
    daily_bonus_eligible: Optional[bool] = None
    daily_bonus_amount: Optional[int] = None

    class Config:
        from_attributes = True


# Token models
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    user_id: str
    fairyname: str
    is_admin: bool = False
    exp: Optional[datetime] = None


# Progressive Profiling models - removed (no longer needed)


class PersonInMyLifeCreate(BaseModel):
    name: str = Field(..., max_length=100)
    birth_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    relationship: Optional[str] = Field(None, max_length=100)
    personality_description: Optional[str] = Field(None, max_length=200)


class PersonInMyLifeUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    birth_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    relationship: Optional[str] = Field(None, max_length=100)
    personality_description: Optional[str] = Field(None, max_length=200)


class PersonInMyLife(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    birth_date: Optional[date] = None
    relationship: Optional[str] = None
    personality_description: Optional[str] = None
    photo_url: Optional[str] = None
    photo_uploaded_at: Optional[datetime] = None
    photo_size_bytes: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Person profile data models - removed (no longer needed)


# Migration and batch operation models - removed (no longer needed)


# Onboard tracking models
class OnboardTracking(BaseModel):
    user_id: UUID
    has_used_inspire: bool = False
    has_completed_first_inspiration: bool = False
    onboarding_step: Optional[str] = None
    has_seen_inspire_tip: bool = False
    has_seen_inspire_result_tip: bool = False
    has_seen_onboarding_complete_tip: bool = False

    class Config:
        from_attributes = True


class OnboardTrackingUpdate(BaseModel):
    has_used_inspire: Optional[bool] = None
    has_completed_first_inspiration: Optional[bool] = None
    onboarding_step: Optional[str] = None
    has_seen_inspire_tip: Optional[bool] = None
    has_seen_inspire_result_tip: Optional[bool] = None
    has_seen_onboarding_complete_tip: Optional[bool] = None


# Referral models
class ReferralCodeResponse(BaseModel):
    referral_code: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


# Response models
class AuthResponse(BaseModel):
    user: User
    token: Token
    is_new_user: bool = False
    dust_granted: int = 0
    # Daily login bonus eligibility info
    is_first_login_today: bool = False
    daily_bonus_eligible: bool = False


# Account deletion models
class AccountDeletionRequest(BaseModel):
    reason: Literal["not_using_anymore", "privacy_concerns", "too_expensive", "switching_platform", "other"]
    feedback: Optional[str] = Field(None, max_length=1000)


class AccountDeletionResponse(BaseModel):
    message: str
    deletion_id: str
