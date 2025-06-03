from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Literal
from datetime import datetime
import re
from uuid import UUID

# Auth models
class OTPRequest(BaseModel):
    identifier: str  # Email or phone number
    identifier_type: Literal["email", "phone"]
    
    @validator("identifier")
    def validate_identifier(cls, v, values):
        if values.get("identifier_type") == "email":
            # Basic email validation
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
                raise ValueError("Invalid email format")
        elif values.get("identifier_type") == "phone":
            # Basic phone validation (E.164 format)
            if not re.match(r"^\+[1-9]\d{1,14}$", v):
                raise ValueError("Phone must be in E.164 format (e.g., +1234567890)")
        return v

class OTPVerify(BaseModel):
    identifier: str
    code: str = Field(..., min_length=6, max_length=6)
    
    @validator("code")
    def validate_code(cls, v):
        if not v.isdigit():
            raise ValueError("OTP code must contain only digits")
        return v

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

class User(BaseModel):
    id: UUID
    fairyname: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_builder: bool = False
    is_active: bool = True
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
    exp: Optional[datetime] = None

# Response models
class AuthResponse(BaseModel):
    user: User
    token: Token
    is_new_user: bool = False
    dust_granted: int = 0