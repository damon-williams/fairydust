# services/ledger/routes.py
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from ledger_service import LedgerService
from models import (
    AppInitialGrantRequest,
    Balance,
    BalanceAdjustment,
    BulkGrantRequest,
    ConsumeRequest,
    DailyBonusGrantRequest,
    GrantRequest,
    InAppPurchaseRequest,
    PromotionalGrantRequest,
    PurchaseRequest,
    ReferralRewardGrantRequest,
    RefundRequest,
    TransactionList,
    TransactionResponse,
    TransactionType,
    UserStats,
)

from shared.auth_middleware import TokenData, get_current_user, require_admin
from shared.database import Database, get_db
from shared.redis_client import get_redis

# Create routers
balance_router = APIRouter()
transaction_router = APIRouter()
admin_router = APIRouter()
grants_router = APIRouter()


# Helper functions
async def get_action_pricing(action_slug: str, cache: redis.Redis) -> Optional[int]:
    """Get DUST cost for action from pricing service with caching"""
    try:
        # Try to get from cache first (TTL: 5 minutes)
        cached_price = await cache.get(f"action_pricing:{action_slug}")
        if cached_price:
            return int(cached_price)

        # Fetch from apps service pricing API
        apps_service_url = os.getenv("APPS_SERVICE_URL", "http://localhost:8003")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{apps_service_url}/apps/pricing/actions", timeout=5.0)

            if response.status_code == 200:
                pricing_data = response.json()

                # Cache all pricing data for 5 minutes
                for slug, data in pricing_data.items():
                    await cache.setex(f"action_pricing:{slug}", 300, str(data["dust"]))

                # Return the requested action price
                if action_slug in pricing_data:
                    return pricing_data[action_slug]["dust"]

        return None  # Action not found or service unavailable

    except Exception as e:
        print(f"⚠️ Failed to fetch action pricing for '{action_slug}': {e}", flush=True)
        return None  # Allow consumption with client-provided amount if pricing unavailable


# Dependency to get ledger service
async def get_ledger_service(
    db: Database = Depends(get_db), redis_client: redis.Redis = Depends(get_redis)
) -> LedgerService:
    return LedgerService(db, redis_client)


# Balance Routes
@balance_router.get("/{user_id}", response_model=Balance)
async def get_balance(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
    db: Database = Depends(get_db),
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
        user_id,
    )

    return Balance(
        user_id=user_id,
        balance=balance,
        pending_balance=pending_result["pending"],
        last_updated=datetime.utcnow(),
    )


@balance_router.get("/check/{user_id}")
async def check_balance_sufficient(
    user_id: UUID,
    amount: int = Query(..., gt=0),
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Check if user has sufficient balance for an action"""
    # This endpoint is for apps to check before attempting consume

    balance = await ledger.get_balance(user_id)

    return {"sufficient": balance >= amount, "balance": balance, "required": amount}


# Transaction Routes
@transaction_router.post("/consume", response_model=TransactionResponse)
async def consume_dust(
    request: ConsumeRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """Consume DUST for an app action"""

    # Resolve app slug to UUID if needed
    app_uuid = await resolve_app_id(request.app_id, db, cache)
    print(f"🎨 CONSUME: Resolved app '{request.app_id}' to UUID {app_uuid}", flush=True)

    # Validate the app
    app_validation = await validate_app(app_uuid)

    if not app_validation["is_valid"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    if not app_validation["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="App is not active or not approved"
        )

    # Validate action pricing if action is provided
    if request.action:
        expected_amount = await get_action_pricing(request.action, cache)
        if expected_amount is not None and request.amount != expected_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid DUST amount for action '{request.action}'. Expected: {expected_amount}, Provided: {request.amount}",
            )

    # Verify the user has enough DUST
    ledger = LedgerService(db, cache)
    balance = await ledger.get_balance(request.user_id)

    if balance < request.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient DUST balance. Required: {request.amount}, Available: {balance}",
        )

    # Process the consumption (pass resolved UUID)
    transaction = await ledger.consume_dust(
        user_id=request.user_id,
        amount=request.amount,
        app_id=app_uuid,
        action=request.action,
        idempotency_key=request.idempotency_key,
        metadata=request.metadata,
    )

    return transaction


@transaction_router.post("/purchase", response_model=TransactionResponse)
async def record_purchase(
    request: PurchaseRequest,
    current_user: TokenData = Depends(require_admin),  # Only admin/system can record purchases
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Record a DUST purchase (called by billing service)"""
    return await ledger.record_purchase(
        user_id=request.user_id,
        dust_amount=request.amount,
        payment_id=request.payment_id,
        payment_amount_cents=request.payment_amount_cents,
    )


@transaction_router.post("/purchase/in-app", response_model=TransactionResponse)
async def process_in_app_purchase(
    request: InAppPurchaseRequest,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Process in-app purchase from mobile app stores with receipt verification"""
    # Users can only make purchases for themselves
    user_id = UUID(current_user.user_id)

    print(f"🍎 IN_APP_PURCHASE: ========== PURCHASE REQUEST RECEIVED ===========")
    print(f"🍎 IN_APP_PURCHASE: Client initiated purchase request")
    print(f"🍎 IN_APP_PURCHASE: Platform: {request.platform}")
    print(f"🍎 IN_APP_PURCHASE: User ID: {user_id}")
    print(f"🍎 IN_APP_PURCHASE: User token sub: {current_user.user_id}")
    print(f"🍎 IN_APP_PURCHASE: Product ID: {request.product_id}")
    print(f"🍎 IN_APP_PURCHASE: Receipt data length: {len(request.receipt_data)} chars")
    print(f"🍎 IN_APP_PURCHASE: Receipt preview: {request.receipt_data[:50]}...")
    print(f"🍎 IN_APP_PURCHASE: Request timestamp: {datetime.utcnow().isoformat()}")
    print(f"🍎 IN_APP_PURCHASE: User agent: {current_user}")

    # Validate platform early
    if request.platform not in ["ios", "android"]:
        print(f"🍎 IN_APP_PURCHASE: ❌ Invalid platform rejected: {request.platform}")
        raise HTTPException(
            status_code=400,
            detail="Invalid platform. Must be 'ios' or 'android'"
        )
    
    print(f"🍎 IN_APP_PURCHASE: Platform validation passed: {request.platform}")
    
    if request.platform == "ios":
        print(f"🍎 IN_APP_PURCHASE: Initializing Apple receipt verification service")
        # Use Apple receipt verification
        from apple_receipt_verification import AppleReceiptVerificationService
        
        try:
            apple_service = AppleReceiptVerificationService()
            print(f"🍎 IN_APP_PURCHASE: ✅ Apple service initialized successfully")
        except Exception as e:
            print(f"🍎 IN_APP_PURCHASE: ❌ Failed to initialize Apple service: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to initialize receipt verification service"
            )
        
        # Verify receipt with Apple
        print(f"🍎 IN_APP_PURCHASE: Starting Apple receipt verification process")
        try:
            is_valid, verification_response, error_message = await apple_service.verify_receipt(
                request.receipt_data, request.product_id
            )
            print(f"🍎 IN_APP_PURCHASE: Verification process completed - Valid: {is_valid}")
        except Exception as e:
            print(f"🍎 IN_APP_PURCHASE: ❌ Exception during Apple verification: {str(e)}")
            print(f"🍎 IN_APP_PURCHASE: Exception type: {type(e).__name__}")
            raise HTTPException(
                status_code=500,
                detail="Receipt verification service error"
            )
        
        if not is_valid:
            print(f"🍎 IN_APP_PURCHASE: ❌ Apple verification failed: {error_message}")
            print(f"🍎 IN_APP_PURCHASE: Verification response: {verification_response}")
            raise HTTPException(
                status_code=400, 
                detail=f"Receipt verification failed: {error_message}"
            )
        
        print("🍎 IN_APP_PURCHASE: ✅ Apple receipt verification successful")
        
        # Extract transaction data from Apple response
        print(f"🍎 IN_APP_PURCHASE: Extracting transaction data from Apple response")
        try:
            apple_transaction_data = apple_service.extract_transaction_data(
                verification_response, request.product_id
            )
            
            dust_amount = apple_transaction_data["dust_amount"]
            print(f"🍎 IN_APP_PURCHASE: DUST amount to grant: {dust_amount}")
            
            # Generate payment ID
            import secrets
            purchase_id = f"ios_{request.product_id}_{secrets.token_hex(8)}"
            print(f"🍎 IN_APP_PURCHASE: Generated payment ID: {purchase_id}")
            
            # Record the verified purchase
            print(f"🍎 IN_APP_PURCHASE: Recording purchase in ledger...")
            result = await ledger.record_apple_purchase(
                user_id=user_id,
                dust_amount=dust_amount,
                payment_id=purchase_id,
                receipt_data=request.receipt_data,
                verification_status="verified",
                verification_response=verification_response,
                apple_transaction_data=apple_transaction_data,
                payment_amount_cents=dust_amount,  # 1 DUST = 1 cent
            )
            
            print(f"🍎 IN_APP_PURCHASE: ✅ Purchase recorded successfully - Transaction ID: {result.transaction_id}")
            print(f"🍎 IN_APP_PURCHASE: New balance: {result.new_balance} DUST")
            print(f"🍎 IN_APP_PURCHASE: ========== PURCHASE COMPLETE ===========")
            return result
            
        except Exception as e:
            print(f"🍎 IN_APP_PURCHASE: ❌ Error during purchase processing: {str(e)}")
            print(f"🍎 IN_APP_PURCHASE: Error type: {type(e).__name__}")
            raise
        
    elif request.platform == "android":
        print(f"🤖 IN_APP_PURCHASE: Android platform requested but not implemented")
        # TODO: Implement Google Play receipt verification
        raise HTTPException(
            status_code=501, 
            detail="Android receipt verification not yet implemented"
        )
    
    # This should never execute due to early validation, but kept for safety
    else:
        print(f"🍎 IN_APP_PURCHASE: ❌ Unexpected platform bypass: {request.platform}")
        raise HTTPException(
            status_code=400,
            detail="Invalid platform. Must be 'ios' or 'android'"
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
    db: Database = Depends(get_db),
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
        app_id=app_id,
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
        transactions=transactions, total=total, page=page, page_size=page_size, has_more=has_more
    )


@transaction_router.get("/stats/{user_id}", response_model=UserStats)
async def get_user_stats(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
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
        user_id,
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
            favorite_app_id=None,
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
        user_id,
    )

    return UserStats(**stats, favorite_app_id=favorite_app["app_id"] if favorite_app else None)


# Admin Routes
@admin_router.post("/grant", response_model=TransactionResponse)
async def grant_dust(
    request: GrantRequest,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Grant DUST to a user (admin only)"""
    return await ledger.grant_dust(
        user_id=request.user_id,
        amount=request.amount,
        reason=request.reason,
        admin_id=UUID(current_user.user_id),
        metadata=request.metadata,
    )


@admin_router.post("/bulk-grant")
async def bulk_grant_dust(
    request: BulkGrantRequest,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service),
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
                admin_id=request.admin_id,
            )
            results.append({"user_id": user_id, "success": True, "new_balance": result.new_balance})
        except Exception as e:
            errors.append({"user_id": user_id, "success": False, "error": str(e)})

    return {
        "total": len(request.user_ids),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


@admin_router.post("/refund", response_model=TransactionResponse)
async def refund_transaction(
    request: RefundRequest,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Refund a transaction (admin only)"""
    return await ledger.refund_transaction(
        transaction_id=request.transaction_id,
        reason=request.reason,
        admin_id=UUID(current_user.user_id),
    )


@admin_router.post("/adjust-balance", response_model=TransactionResponse)
async def adjust_balance(
    request: BalanceAdjustment,
    current_user: TokenData = Depends(require_admin),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Manually adjust a user's balance (admin only)"""
    if request.adjustment > 0:
        return await ledger.grant_dust(
            user_id=request.user_id,
            amount=request.adjustment,
            reason=f"Manual adjustment: {request.reason}",
            admin_id=request.admin_id,
        )
    else:
        # For negative adjustments, we need to implement a deduct method
        # For now, raise an error
        raise HTTPException(status_code=501, detail="Negative adjustments not yet implemented")


@admin_router.delete("/testing/reset-grants/{user_id}")
async def reset_user_grants(
    user_id: UUID,
    current_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Reset all grants for a user (testing only)"""
    import os

    if os.getenv("ENVIRONMENT") != "development":
        raise HTTPException(status_code=403, detail="Only available in development environment")

    # Delete all grants for the user
    result = await db.execute("DELETE FROM app_grants WHERE user_id = $1", user_id)

    return {
        "success": True,
        "message": f"Reset all grants for user {user_id}",
        "grants_deleted": result,
    }


@admin_router.get("/analytics/app/{app_id}")
async def get_app_analytics(
    app_id: UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
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
        app_id,
        start_date,
        end_date,
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
        app_id,
        start_date,
        end_date,
    )

    return {
        "app_id": app_id,
        "period": {"start": start_date, "end": end_date},
        "summary": stats,
        "daily_breakdown": daily_stats,
    }


async def resolve_app_id(app_id_or_slug: str, db: Database, cache: redis.Redis) -> UUID:
    """Resolve app slug to UUID, with Redis caching"""
    from uuid import UUID

    # Try to parse as UUID first
    try:
        return UUID(app_id_or_slug)
    except ValueError:
        pass

    # It's a slug, try cache first
    cache_key = f"app_slug:{app_id_or_slug}"
    try:
        cached_id = await cache.get(cache_key)
        if cached_id:
            print(f"🔍 SLUG_CACHE: Hit for {app_id_or_slug} -> {cached_id.decode()}", flush=True)
            return UUID(cached_id.decode())
    except Exception as e:
        print(f"⚠️ SLUG_CACHE: Cache error: {e}", flush=True)

    # Cache miss, query database
    print(f"🔍 SLUG_RESOLVE: Resolving slug '{app_id_or_slug}' to UUID", flush=True)
    result = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", app_id_or_slug)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"App with slug '{app_id_or_slug}' not found",
        )

    app_uuid = result["id"]

    # Cache the result for 5 minutes
    try:
        await cache.setex(cache_key, 300, str(app_uuid))
        print(f"✅ SLUG_CACHE: Cached {app_id_or_slug} -> {app_uuid}", flush=True)
    except Exception as e:
        print(f"⚠️ SLUG_CACHE: Cache set error: {e}", flush=True)

    return app_uuid


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


# App Grant Routes
@grants_router.post("/app-initial", response_model=TransactionResponse)
async def grant_initial_dust(
    request: AppInitialGrantRequest,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
    db: Database = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """Grant initial DUST to user for app onboarding (app-initiated)"""

    # Resolve app slug to UUID if needed
    app_uuid = await resolve_app_id(request.app_id, db, cache)
    print(f"🎨 GRANT_INITIAL: Resolved app '{request.app_id}' to UUID {app_uuid}", flush=True)

    # Validate the app
    app_validation = await validate_app(app_uuid)

    if not app_validation["is_valid"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    if not app_validation["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="App is not active or not approved"
        )

    # Apps can only grant to any user, but we'll validate the user exists
    return await ledger.grant_initial_dust(
        user_id=request.user_id,
        app_id=app_uuid,
        amount=request.amount,
        idempotency_key=request.idempotency_key,
    )


@grants_router.post("/daily-bonus", response_model=TransactionResponse)
async def grant_daily_bonus(
    request: DailyBonusGrantRequest,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
    db: Database = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """Grant daily login bonus to user (app-initiated)"""

    # Resolve app slug to UUID if needed
    app_uuid = await resolve_app_id(request.app_id, db, cache)
    print(f"🎨 GRANT_DAILY_BONUS: Resolved app '{request.app_id}' to UUID {app_uuid}", flush=True)

    # Validate the app
    app_validation = await validate_app(app_uuid)

    if not app_validation["is_valid"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")

    if not app_validation["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="App is not active or not approved"
        )

    # Get daily bonus amount from system config
    config_result = await db.fetch_one(
        "SELECT value FROM system_config WHERE key = 'daily_login_bonus_amount'"
    )

    if not config_result:
        raise HTTPException(status_code=500, detail="Daily bonus not configured")

    bonus_amount = int(config_result["value"])

    # Apps can grant daily bonuses to any user
    return await ledger.grant_daily_bonus(
        user_id=request.user_id,
        app_id=app_uuid,
        amount=bonus_amount,
        idempotency_key=request.idempotency_key,
    )


@grants_router.post("/referral-reward", response_model=TransactionResponse)
async def grant_referral_reward(
    request: ReferralRewardGrantRequest,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
    db: Database = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """Grant DUST for referral rewards"""

    # Get fairydust-invite app UUID
    invite_app_uuid = await resolve_app_id("fairydust-invite", db, cache)
    print(f"🎁 REFERRAL_REWARD: Using fairydust-invite app UUID {invite_app_uuid}", flush=True)

    # Validate the invite app exists
    app_validation = await validate_app(invite_app_uuid)

    if not app_validation["is_valid"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite app not found")

    if not app_validation["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invite app is not active"
        )

    # Create transaction description based on reward reason
    reason_descriptions = {
        "referral_bonus": "Referral bonus for successful invite",
        "referee_bonus": "Welcome bonus for using referral code",
        "milestone_bonus": f"Milestone bonus for {request.amount} DUST achievement",
    }

    description = reason_descriptions.get(request.reason, f"Referral reward: {request.reason}")

    # Grant the referral reward using the standard grant mechanism
    return await ledger.grant_dust(
        user_id=request.user_id,
        amount=request.amount,
        reason=description,
        metadata={
            "reward_type": request.reason,
            "referral_id": str(request.referral_id),
        },
    )


@grants_router.post("/promotional", response_model=TransactionResponse)
async def grant_promotional_dust(
    request: PromotionalGrantRequest,
    current_user: TokenData = Depends(get_current_user),
    ledger: LedgerService = Depends(get_ledger_service),
):
    """Grant DUST for promotional code redemption (service-to-service)"""

    # Grant promotional DUST using the standard grant mechanism
    return await ledger.grant_dust(
        user_id=request.user_id,
        amount=request.amount,
        reason=request.reason,
        metadata={
            "promotional_code": request.promotional_code,
            "idempotency_key": request.idempotency_key,
        },
    )
