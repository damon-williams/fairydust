# services/apps/models.py
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum

class AppStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"

class AppCategory(str, Enum):
    PRODUCTIVITY = "productivity"
    ENTERTAINMENT = "entertainment"
    EDUCATION = "education"
    BUSINESS = "business"
    CREATIVE = "creative"
    UTILITIES = "utilities"
    GAMES = "games"
    OTHER = "other"

# Basic Models for Testing
class AppCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    icon_url: Optional[str] = None
    category: AppCategory
    website_url: Optional[str] = None
    demo_url: Optional[str] = None
    callback_url: Optional[str] = None

class App(BaseModel):
    id: UUID
    builder_id: UUID
    name: str
    slug: str
    description: str
    icon_url: Optional[str]
    category: AppCategory
    website_url: Optional[str]
    demo_url: Optional[str]
    callback_url: Optional[str]
    status: AppStatus
    is_active: bool
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

class AppValidation(BaseModel):
    """Response for ledger service validation"""
    app_id: UUID
    is_valid: bool
    is_active: bool
    name: str
    builder_id: UUID