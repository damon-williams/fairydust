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

# LLM Architecture Models
class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"

class ModelParameters(BaseModel):
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=8000)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)

class FallbackModel(BaseModel):
    provider: LLMProvider
    model_id: str = Field(..., max_length=100)
    trigger: str = Field(..., max_length=50)  # "provider_error", "cost_threshold_exceeded", etc.
    parameters: ModelParameters = Field(default_factory=ModelParameters)

class CostLimits(BaseModel):
    per_request_max: Optional[float] = Field(None, gt=0)
    daily_max: Optional[float] = Field(None, gt=0)
    monthly_max: Optional[float] = Field(None, gt=0)

class FeatureFlags(BaseModel):
    streaming_enabled: bool = True
    cache_responses: bool = True
    log_prompts: bool = False

class AppModelConfig(BaseModel):
    id: UUID
    app_id: str
    primary_provider: LLMProvider
    primary_model_id: str = Field(..., max_length=100)
    primary_parameters: ModelParameters
    fallback_models: list[FallbackModel] = Field(default_factory=list)
    cost_limits: CostLimits = Field(default_factory=CostLimits)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AppModelConfigCreate(BaseModel):
    primary_provider: LLMProvider
    primary_model_id: str = Field(..., max_length=100)
    primary_parameters: ModelParameters = Field(default_factory=ModelParameters)
    fallback_models: list[FallbackModel] = Field(default_factory=list)
    cost_limits: CostLimits = Field(default_factory=CostLimits)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)

class AppModelConfigUpdate(BaseModel):
    primary_provider: Optional[LLMProvider] = None
    primary_model_id: Optional[str] = Field(None, max_length=100)
    primary_parameters: Optional[ModelParameters] = None
    fallback_models: Optional[list[FallbackModel]] = None
    cost_limits: Optional[CostLimits] = None
    feature_flags: Optional[FeatureFlags] = None

class LLMUsageLogCreate(BaseModel):
    user_id: UUID
    app_id: str = Field(..., max_length=255)
    provider: LLMProvider
    model_id: str = Field(..., max_length=100)
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    # cost_usd: REMOVED - calculated server-side only for security
    latency_ms: int = Field(..., ge=0)
    prompt_hash: Optional[str] = Field(None, max_length=64)
    finish_reason: Optional[str] = Field(None, max_length=50)
    was_fallback: bool = False
    fallback_reason: Optional[str] = Field(None, max_length=100)
    request_metadata: dict = Field(default_factory=dict)

class LLMUsageLog(BaseModel):
    id: UUID
    user_id: UUID
    app_id: str
    provider: LLMProvider
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    prompt_hash: Optional[str]
    finish_reason: Optional[str]
    was_fallback: bool
    fallback_reason: Optional[str]
    request_metadata: dict
    created_at: datetime
    
    class Config:
        from_attributes = True

class LLMUsageStats(BaseModel):
    total_requests: int
    total_tokens: int
    total_cost_usd: float
    average_latency_ms: float
    model_breakdown: dict[str, dict[str, int | float]]
    period_start: datetime
    period_end: datetime