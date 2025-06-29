import re
from datetime import datetime
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
    avatar_url: Optional[str] = None
    first_name: Optional[str] = Field(None, max_length=100)
    age_range: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)


class User(BaseModel):
    id: UUID
    fairyname: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_builder: bool = False
    is_admin: bool = False
    is_active: bool = True
    is_onboarding_completed: bool = False
    first_name: Optional[str] = None
    age_range: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    last_profiling_session: Optional[datetime] = None
    total_profiling_sessions: int = 0
    created_at: datetime
    updated_at: datetime
    dust_balance: int = 0  # Denormalized for performance

    class Config:
        from_attributes = True


class UserPublic(BaseModel):
    id: UUID
    fairyname: str
    avatar_url: Optional[str] = None
    is_builder: bool
    created_at: datetime


# Token models
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    user_id: str
    fairyname: str
    is_builder: bool = False
    is_admin: bool = False
    exp: Optional[datetime] = None


# Progressive Profiling models
class UserProfileDataCreate(BaseModel):
    category: str = Field(..., max_length=50)
    field_name: str = Field(..., max_length=100)
    field_value: dict | list | str | int | float | bool
    confidence_score: float = Field(1.0, ge=0.0, le=1.0)
    source: str = Field("user_input", max_length=50)
    app_context: Optional[str] = Field(None, max_length=50)


class UserProfileDataUpdate(BaseModel):
    field_value: Optional[dict | list | str | int | float | bool] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    source: Optional[str] = Field(None, max_length=50)
    app_context: Optional[str] = Field(None, max_length=50)


class UserProfileData(BaseModel):
    id: UUID
    user_id: UUID
    category: str
    field_name: str
    field_value: dict | list | str | int | float | bool
    confidence_score: float
    source: str
    app_context: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PersonInMyLifeCreate(BaseModel):
    name: str = Field(..., max_length=100)
    age_range: Optional[str] = Field(None, max_length=50)
    relationship: Optional[str] = Field(None, max_length=100)


class PersonInMyLifeUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    age_range: Optional[str] = Field(None, max_length=50)
    relationship: Optional[str] = Field(None, max_length=100)


class PersonInMyLife(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    age_range: Optional[str] = None
    relationship: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PersonProfileDataCreate(BaseModel):
    category: str = Field(..., max_length=50)
    field_name: str = Field(..., max_length=100)
    field_value: dict | list | str | int | float | bool
    confidence_score: float = Field(1.0, ge=0.0, le=1.0)
    source: str = Field("user_input", max_length=50)


class PersonProfileData(BaseModel):
    id: UUID
    person_id: UUID
    user_id: UUID
    category: str
    field_name: str
    field_value: dict | list | str | int | float | bool
    confidence_score: float
    source: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Migration models
class LocalProfileData(BaseModel):
    id: str
    profile: dict
    people_in_my_life: list[dict]


# Batch operations
class ProfileDataBatch(BaseModel):
    profile_data: list[UserProfileDataCreate]


# Response models
class AuthResponse(BaseModel):
    user: User
    token: Token
    is_new_user: bool = False
    dust_granted: int = 0
