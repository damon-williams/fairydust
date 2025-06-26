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
    app_id: UUID
    action: str = Field(..., description="Action being performed")
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    metadata: Optional[dict[str, Any]] = None

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
