# services/ledger/models.py
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


# Enums
class TransactionType(str, Enum):
    GRANT = "grant"
    CONSUME = "consume"
    PURCHASE = "purchase"
    REFUND = "refund"
    TRANSFER = "transfer"  # For future peer-to-peer


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


# Request models
class ConsumeRequest(BaseModel):
    user_id: UUID
    amount: int = Field(..., gt=0, description="Amount of DUST to consume")
    app_id: str = Field(..., description="App UUID or slug (e.g., 'fairydust-fortune-teller')")
    action: str = Field(..., description="Action being performed")
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    metadata: Optional[dict[str, Any]] = None

    @validator("app_id")
    def validate_app_id(cls, v):
        # Accept either UUID format or slug format
        import re
        from uuid import UUID

        # Try to parse as UUID first
        try:
            UUID(v)
            return v  # Valid UUID
        except ValueError:
            pass

        # Check if it's a valid slug format (alphanumeric with hyphens)
        if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$", v) and len(v) <= 255:
            return v  # Valid slug

        raise ValueError("app_id must be a valid UUID or slug (e.g., 'fairydust-fortune-teller')")

    @validator("idempotency_key")
    def validate_idempotency_key(cls, v):
        # Ensure idempotency key is alphanumeric with some special chars
        import re

        if not re.match(r"^[a-zA-Z0-9_\-:]+$", v):
            raise ValueError("Idempotency key must be alphanumeric with -_: allowed")
        return v


class GrantRequest(BaseModel):
    user_id: UUID
    amount: int = Field(..., gt=0, le=10000, description="Amount of DUST to grant")
    reason: str = Field(..., min_length=1, max_length=255)
    metadata: Optional[dict[str, Any]] = None
    admin_id: Optional[UUID] = None


class AppInitialGrantRequest(BaseModel):
    user_id: UUID
    app_id: str = Field(..., description="App UUID or slug")
    amount: int = Field(..., ge=1, le=100, description="Initial DUST amount (max 100)")
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @validator("app_id")
    def validate_app_id(cls, v):
        # Accept either UUID format or slug format
        import re
        from uuid import UUID

        try:
            UUID(v)
            return v  # Valid UUID
        except ValueError:
            pass

        if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$", v) and len(v) <= 255:
            return v  # Valid slug

        raise ValueError("app_id must be a valid UUID or slug")

    @validator("idempotency_key")
    def validate_idempotency_key(cls, v):
        import re

        if not re.match(r"^[a-zA-Z0-9_\-:]+$", v):
            raise ValueError("Idempotency key must be alphanumeric with -_: allowed")
        return v


class AppStreakGrantRequest(BaseModel):
    user_id: UUID
    app_id: str = Field(..., description="App UUID or slug")
    amount: int = Field(..., ge=1, le=25, description="Daily bonus amount (max 25)")
    streak_days: int = Field(..., ge=1, le=5, description="Current streak for validation")
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @validator("app_id")
    def validate_app_id(cls, v):
        # Accept either UUID format or slug format
        import re
        from uuid import UUID

        try:
            UUID(v)
            return v  # Valid UUID
        except ValueError:
            pass

        if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$", v) and len(v) <= 255:
            return v  # Valid slug

        raise ValueError("app_id must be a valid UUID or slug")

    @validator("idempotency_key")
    def validate_idempotency_key(cls, v):
        import re

        if not re.match(r"^[a-zA-Z0-9_\-:]+$", v):
            raise ValueError("Idempotency key must be alphanumeric with -_: allowed")
        return v


class ReferralRewardGrantRequest(BaseModel):
    user_id: UUID
    amount: int = Field(..., ge=1, le=100, description="Referral reward amount")
    reason: str = Field(..., description="Type of referral reward: referral_bonus|referee_bonus|milestone_bonus")
    referral_id: UUID = Field(..., description="Referral redemption ID for tracking")
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @validator("reason")
    def validate_reason(cls, v):
        allowed_reasons = ["referral_bonus", "referee_bonus", "milestone_bonus"]
        if v not in allowed_reasons:
            raise ValueError(f"Reason must be one of: {', '.join(allowed_reasons)}")
        return v

    @validator("idempotency_key")
    def validate_idempotency_key(cls, v):
        import re

        if not re.match(r"^[a-zA-Z0-9_\-:]+$", v):
            raise ValueError("Idempotency key must be alphanumeric with -_: allowed")
        return v


class PromotionalGrantRequest(BaseModel):
    user_id: UUID
    amount: int = Field(..., ge=1, le=1000, description="Promotional grant amount")
    reason: str = Field(..., min_length=1, max_length=255)
    promotional_code: str = Field(..., min_length=1, max_length=50)
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @validator("idempotency_key")
    def validate_idempotency_key(cls, v):
        import re

        if not re.match(r"^[a-zA-Z0-9_\-:]+$", v):
            raise ValueError("Idempotency key must be alphanumeric with -_: allowed")
        return v


class RefundRequest(BaseModel):
    transaction_id: UUID
    reason: str = Field(..., min_length=1, max_length=255)
    admin_id: Optional[UUID] = None


class PurchaseRequest(BaseModel):
    user_id: UUID
    amount: int = Field(..., gt=0, description="Amount of DUST purchased")
    payment_id: str = Field(..., description="Stripe payment intent ID")
    payment_amount_cents: int = Field(..., gt=0, description="Amount paid in cents")


# Response models
class Balance(BaseModel):
    user_id: UUID
    balance: int = Field(..., ge=0)
    pending_balance: int = Field(0, ge=0, description="Balance in pending transactions")
    last_updated: datetime


class Transaction(BaseModel):
    id: UUID
    user_id: UUID
    amount: int
    type: TransactionType
    status: TransactionStatus
    description: str
    app_id: Optional[UUID] = None
    metadata: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    transaction: Transaction
    new_balance: int
    previous_balance: int


class TransactionList(BaseModel):
    transactions: list[Transaction]
    total: int
    page: int
    page_size: int
    has_more: bool


# Admin models
class BulkGrantRequest(BaseModel):
    user_ids: list[UUID] = Field(..., min_items=1, max_items=1000)
    amount: int = Field(..., gt=0, le=1000)
    reason: str = Field(..., min_length=1, max_length=255)
    admin_id: UUID


class BalanceAdjustment(BaseModel):
    user_id: UUID
    adjustment: int = Field(..., description="Positive or negative adjustment")
    reason: str = Field(..., min_length=1, max_length=255)
    admin_id: UUID


# Analytics models
class UserStats(BaseModel):
    user_id: UUID
    total_granted: int
    total_consumed: int
    total_purchased: int
    total_refunded: int
    transaction_count: int
    first_transaction: Optional[datetime]
    last_transaction: Optional[datetime]
    favorite_app_id: Optional[UUID]


class AppStats(BaseModel):
    app_id: UUID
    total_consumed: int
    unique_users: int
    transaction_count: int
    avg_consumption: float
    period_start: datetime
    period_end: datetime


# Cache models
class CachedBalance(BaseModel):
    balance: int
    version: int
    expires_at: datetime
