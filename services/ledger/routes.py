# services/ledger/routes.py
import httpx
import os
from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from models import (
    Balance, ConsumeRequest, GrantRequest, RefundRequest, PurchaseRequest,
    TransactionResponse, TransactionList, TransactionType,
    BulkGrantRequest, BalanceAdjustment, UserStats
)
from ledger_service import LedgerService
from shared.database import get_db, Database
from shared.redis_client import get_redis
from shared.auth_middleware import get_current_user, require_admin, TokenData
import redis.asyncio as redis

# Create routers
balance_router = APIRouter()
transaction_router = APIRouter()
admin_router = APIRouter()

# Dependency to get ledger service
async def get_ledger_service(
    db: Database = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
) -> LedgerService:
    return LedgerService(db, redis_client)

# Balance Routes
@balance_router.get("/{user_id}", response_model=Balance)
async def get_balance(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
    db: Database = Depends(get_db)
):
    """Get user's current DUST balance"""
    # Users can only check their own balance unless they're an admin
    if str(user_id) != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot view other users' balances")
    
    balance = await ledger.get_balance(user_id)
    
    # Get pending balance (transactions in progress)
    pending_result = await db.fetch_one(
        """
        SELECT COALESCE(SUM(ABS(amount)), 0) as pending
        FROM dust_transactions
        WHERE user_id = $1 AND status = 'pending'
        """,
        user_id
    )
    
    return Balance(
        user_id=user_id,
        balance=balance,
        pending_balance=pending_result["pending"],
        last_updated=datetime.utcnow()
    )

@balance_router.get("/check/{user_id}")
async def check_balance_sufficient(
    user_id: UUID,
    amount: int = Query(..., gt=0),
    app_id: UUID = Query(...),
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service)
):
    """Check if user has sufficient balance for an action"""
    # This endpoint is for apps to check before attempting consume
    # Verify the app belongs to the current user (builder)
    # In a full implementation, we'd check app ownership
    
    balance = await ledger.get_balance(user_id)
    
    return {
        "sufficient": balance >= amount,
        "balance": balance,
        "required": amount
    }

# Transaction Routes
@transaction_router.post("/consume", response_model=TransactionResponse)
async def consume_dust(
    request: ConsumeRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    cache: redis.Redis = Depends(get_redis)
):
    """Consume DUST for an app action"""
    
    # Validate the app first
    app_validation = await validate_app(request.app_id)
    
    if not app_validation["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found"
        )
    
    if not app_validation["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="App is not active or not approved"
        )
    
    # Verify the user has enough DUST
    ledger = LedgerService(db, cache)
    balance = await ledger.get_balance(request.user_id)
    
    if balance < request.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient DUST balance. Required: {request.amount}, Available: {balance}"
        )
    
    # Process the consumption
    transaction = await ledger.consume_dust(
        user_id=request.user_id,
        amount=request.amount,
        app_id=request.app_id,
        action=request.action,
        idempotency_key=request.idempotency_key,
        metadata=request.metadata
    )
    
    return transaction

@transaction_router.post("/purchase", response_model=TransactionResponse)
async def record_purchase(
    request: PurchaseRequest,
    current_user: TokenData = Depends(require_admin),  # Only admin/system can record purchases
    ledger: LedgerService = Depends(get_ledger_service)
):
    """Record a DUST purchase (called by billing service)"""
    return await ledger.record_purchase(
        user_id=request.user_id,
        dust_amount=request.amount,
        payment_id=request.payment_id,
        payment_amount_cents=request.payment_amount_cents
    )

@transaction_router.get("/{user_id}", response_model=TransactionList)
async def get_transactions(
    user_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    type: Optional[TransactionType] = None,
    app_id: Optional[UUID] = None,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
    db: Database = Depends(get_db)
):
    """Get user's transaction history"""
    # Users can only view their own transactions unless admin
    if str(user_id) != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot view other users' transactions")
    
    offset = (page - 1) * page_size
    
    # Get transactions
    transactions = await ledger.get_transactions(
        user_id=user_id,
        limit=page_size + 1,  # Get one extra to check if there's more
        offset=offset,
        type_filter=type,
        app_id=app_id
    )
    
    # Check if there are more
    has_more = len(transactions) > page_size
    if has_more:
        transactions = transactions[:page_size]
    
    # Get total count
    count_query = "SELECT COUNT(*) as total FROM dust_transactions WHERE user_id = $1"
    params = [user_id]
    
    if type:
        count_query += " AND type = $2"
        params.append(type.value)
    
    if app_id:
        count_query += f" AND app_id = ${len(params) + 1}"
        params.append(app_id)
    
    total_result = await db.fetch_one(count_query, *params)
    total = total_result["total"]
    
    return TransactionList(
        transactions=transactions,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more
    )

@transaction_router.get("/stats/{user_id}", response_model=UserStats)
async def get_user_stats(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get user's transaction statistics"""
    if str(user_id) != current_user.user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot view other users' stats")
    
    stats = await db.fetch_one(
        """
        SELECT 
            user_id,
            SUM(CASE WHEN type = 'grant' THEN amount ELSE 0 END) as total_granted,
            SUM(CASE WHEN type = 'consume' THEN ABS(amount) ELSE 0 END) as total_consumed,
            SUM(CASE WHEN type = 'purchase' THEN amount ELSE 0 END) as total_purchased,
            SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) as total_refunded,
            COUNT(*) as transaction_count,
            MIN(created_at) as first_transaction,
            MAX(created_at) as last_transaction
        FROM dust_transactions
        WHERE user_id = $1
        GROUP BY user_id
        """,
        user_id
    )
    
    if not stats:
        # Return empty stats for user with no transactions
        return UserStats(
            user_id=user_id,
            total_granted=0,
            total_consumed=0,
            total_purchased=0,
            total_refunded=0,
            transaction_count=0,
            first_transaction=None,
            last_transaction=None,
            favorite_app_id=None
        )
    
    # Get favorite app
    favorite_app = await db.fetch_one(
        """
        SELECT app_id, COUNT(*) as usage_count
        FROM dust_transactions
        WHERE user_id = $1 AND type = 'consume' AND app_id IS NOT NULL
        GROUP BY app_id
        ORDER BY usage_count DESC
        LIMIT 1
        """,
        user_id
    )
    
    return UserStats(
        **stats,
        favorite_app_id=favorite_app["app_id"] if favorite_app else None
    )

# Admin Routes
@admin_router.post("/grant", response_model=TransactionResponse)
async def grant_dust(
    request: GrantRequest,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service)
):
    """Grant DUST to a user (admin only)"""
    return await ledger.grant_dust(
        user_id=request.user_id,
        amount=request.amount,
        reason=request.reason,
        admin_id=UUID(current_user.user_id),
        metadata=request.metadata
    )

@admin_router.post("/bulk-grant")
async def bulk_grant_dust(
    request: BulkGrantRequest,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service)
):
    """Grant DUST to multiple users (admin only)"""
    results = []
    errors = []
    
    for user_id in request.user_ids:
        try:
            result = await ledger.grant_dust(
                user_id=user_id,
                amount=request.amount,
                reason=request.reason,
                admin_id=request.admin_id
            )
            results.append({
                "user_id": user_id,
                "success": True,
                "new_balance": result.new_balance
            })
        except Exception as e:
            errors.append({
                "user_id": user_id,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total": len(request.user_ids),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }

@admin_router.post("/refund", response_model=TransactionResponse)
async def refund_transaction(
    request: RefundRequest,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service)
):
    """Refund a transaction (admin only)"""
    return await ledger.refund_transaction(
        transaction_id=request.transaction_id,
        reason=request.reason,
        admin_id=UUID(current_user.user_id)
    )

@admin_router.post("/adjust-balance", response_model=TransactionResponse)
async def adjust_balance(
    request: BalanceAdjustment,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service)
):
    """Manually adjust a user's balance (admin only)"""
    if request.adjustment > 0:
        return await ledger.grant_dust(
            user_id=request.user_id,
            amount=request.adjustment,
            reason=f"Manual adjustment: {request.reason}",
            admin_id=request.admin_id
        )
    else:
        # For negative adjustments, we need to implement a deduct method
        # For now, raise an error
        raise HTTPException(
            status_code=501, 
            detail="Negative adjustments not yet implemented"
        )

@admin_router.get("/analytics/app/{app_id}")
async def get_app_analytics(
    app_id: UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db)
):
    """Get analytics for an app (admin only)"""
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=30)
    if not end_date:
        end_date = datetime.utcnow()
    
    stats = await db.fetch_one(
        """
        SELECT 
            COUNT(DISTINCT user_id) as unique_users,
            COUNT(*) as transaction_count,
            SUM(ABS(amount)) as total_consumed,
            AVG(ABS(amount)) as avg_consumption,
            MIN(created_at) as first_usage,
            MAX(created_at) as last_usage
        FROM dust_transactions
        WHERE app_id = $1 
        AND type = 'consume'
        AND created_at BETWEEN $2 AND $3
        """,
        app_id, start_date, end_date
    )
    
    # Daily breakdown
    daily_stats = await db.fetch_all(
        """
        SELECT 
            DATE(created_at) as date,
            COUNT(DISTINCT user_id) as unique_users,
            COUNT(*) as transactions,
            SUM(ABS(amount)) as dust_consumed
        FROM dust_transactions
        WHERE app_id = $1 
        AND type = 'consume'
        AND created_at BETWEEN $2 AND $3
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """,
        app_id, start_date, end_date
    )
    
    return {
        "app_id": app_id,
        "period": {
            "start": start_date,
            "end": end_date
        },
        "summary": stats,
        "daily_breakdown": daily_stats
    }

async def validate_app(app_id: UUID) -> dict:
    """Validate app with Apps Service"""
    apps_service_url = os.getenv("APPS_SERVICE_URL", "http://localhost:8003")
    
    # Add logging
    print(f"APPS_SERVICE_URL: {apps_service_url}")
    full_url = f"{apps_service_url}/apps/validate/{app_id}"
    print(f"Validating app at: {full_url}")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(full_url)
            print(f"Apps service response status: {response.status_code}")
            print(f"Apps service response body: {response.text[:200]}...")  # First 200 chars
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"is_valid": False, "is_active": False}
        except Exception as e:
            # If apps service is down, reject the transaction
            print(f"Error validating app {app_id}: {e}")
            return {"is_valid": False, "is_active": False}
        
