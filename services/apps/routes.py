# services/apps/routes.py
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models import (
    App,
    AppCreate,
    AppModelConfig,
    AppModelConfigUpdate,
    AppStatus,
    AppValidation,
    LLMUsageLogCreate,
    LLMUsageStats,
    PromotionalReferralRedeemRequest,
    PromotionalReferralRedeemResponse,
    PromotionalReferralValidateRequest,
    PromotionalReferralValidateResponse,
    RecentReferral,
    ReferralCompleteRequest,
    ReferralCompleteResponse,
    ReferralStatsResponse,
    ReferralValidateRequest,
    ReferralValidateResponse,
)

from shared.auth_middleware import TokenData, get_current_user, require_admin
from shared.database import Database, get_db

# Create routers
app_router = APIRouter()
admin_router = APIRouter()
marketplace_router = APIRouter()
referral_router = APIRouter()

# ============================================================================
# BASIC APP ROUTES
# ============================================================================


@app_router.post("/", response_model=App, status_code=status.HTTP_201_CREATED)
async def create_app(
    app_data: AppCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new app (builders only)"""
    app_id = uuid4()

    # Insert app into database
    await db.execute(
        """
        INSERT INTO apps (
            id, builder_id, name, slug, description, icon_url,
            status, category, website_url, demo_url, callback_url, is_active
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    """,
        app_id,
        UUID(current_user.user_id),
        app_data.name,
        app_data.slug,
        app_data.description,
        app_data.icon_url,
        AppStatus.APPROVED,
        app_data.category,
        app_data.website_url,
        app_data.demo_url,
        app_data.callback_url,
        True,
    )

    # Fetch the created app
    app_result = await db.fetch_one("SELECT * FROM apps WHERE id = $1", app_id)
    return App(**app_result)


@app_router.get("/validate/{app_id}", response_model=AppValidation)
async def validate_app(app_id: UUID, db: Database = Depends(get_db)):
    """Validate app for ledger service"""
    app_data = await db.fetch_one(
        """
        SELECT id, name, builder_id, status, is_active
        FROM apps WHERE id = $1
    """,
        app_id,
    )

    if not app_data:
        return AppValidation(
            app_id=app_id,
            is_valid=False,
            is_active=False,
            name="",
            builder_id=UUID("00000000-0000-0000-0000-000000000000"),
        )

    is_valid = app_data["status"] == AppStatus.APPROVED

    return AppValidation(
        app_id=app_id,
        is_valid=is_valid,
        is_active=app_data["is_active"] and is_valid,
        name=app_data["name"],
        builder_id=app_data["builder_id"],
    )


@admin_router.put("/{app_id}/approve")
async def approve_app(
    app_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Approve an app (admin only)"""
    await db.execute(
        """
        UPDATE apps
        SET status = $1, is_active = $2, updated_at = $3
        WHERE id = $4
    """,
        AppStatus.APPROVED,
        True,
        datetime.utcnow(),
        app_id,
    )

    return {"message": "App approved", "app_id": app_id}


@marketplace_router.get("/")
async def browse_marketplace(db: Database = Depends(get_db)):
    """Simple marketplace endpoint"""
    apps = await db.fetch_all(
        """
        SELECT a.*, u.fairyname as builder_fairyname
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        WHERE a.status = $1 AND a.is_active = $2
        ORDER BY a.created_at DESC
        LIMIT 20
    """,
        AppStatus.APPROVED,
        True,
    )

    return {"apps": apps}


# ============================================================================
# LLM MODEL CONFIGURATION ROUTES
# ============================================================================

llm_router = APIRouter()


@llm_router.get("/{app_id}/model-config", response_model=AppModelConfig)
async def get_app_model_config(app_id: str, db: Database = Depends(get_db)):
    """Get LLM model configuration for an app (with Redis caching)"""
    from shared.app_config_cache import get_app_config_cache
    from shared.json_utils import parse_model_config_field

    # Try to get from cache first
    cache = await get_app_config_cache()
    cached_config = await cache.get_model_config(app_id)

    if cached_config:
        # Parse cached config fields and return
        return AppModelConfig(**cached_config)

    # Cache miss - fetch from database
    config = await db.fetch_one(
        """
        SELECT * FROM app_model_configs WHERE app_id = $1
    """,
        app_id,
    )

    if not config:
        raise HTTPException(
            status_code=404, detail=f"Model configuration not found for app {app_id}"
        )

    # Parse JSONB fields for caching
    config_dict = dict(config)
    parsed_config = {
        "id": str(config_dict["id"]),
        "app_id": config_dict["app_id"],
        "primary_provider": config_dict["primary_provider"],
        "primary_model_id": config_dict["primary_model_id"],
        "primary_parameters": parse_model_config_field(config_dict, "primary_parameters"),
        "fallback_models": parse_model_config_field(config_dict, "fallback_models"),
        "cost_limits": parse_model_config_field(config_dict, "cost_limits"),
        "feature_flags": parse_model_config_field(config_dict, "feature_flags"),
        "is_enabled": config_dict["is_enabled"],
        "created_at": config_dict["created_at"].isoformat() if config_dict["created_at"] else None,
        "updated_at": config_dict["updated_at"].isoformat() if config_dict["updated_at"] else None,
    }

    # Cache the parsed config
    await cache.set_model_config(app_id, parsed_config)

    return AppModelConfig(**config)


@llm_router.put("/{app_id}/model-config", response_model=AppModelConfig)
async def update_app_model_config(
    app_id: str,
    config_update: AppModelConfigUpdate,
    current_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Update LLM model configuration for an app (admin only)"""
    import json

    # Check if app exists
    app = await db.fetch_one("SELECT id FROM apps WHERE id = $1", app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Get current config
    current_config = await db.fetch_one("SELECT * FROM app_model_configs WHERE app_id = $1", app_id)

    # If no configuration exists, create a new one
    if not current_config:
        config_id = uuid4()
        await db.execute(
            """
            INSERT INTO app_model_configs (
                id, app_id, primary_provider, primary_model_id, primary_parameters,
                fallback_models, cost_limits, feature_flags
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)
            """,
            config_id,
            app_id,
            config_update.primary_provider.value if config_update.primary_provider else "anthropic",
            config_update.primary_model_id or "claude-3-5-sonnet-20241022",
            json.dumps(
                config_update.primary_parameters.dict(exclude_none=True)
                if config_update.primary_parameters
                else {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}
            ),
            json.dumps(
                [model.dict(exclude_none=True) for model in config_update.fallback_models]
                if config_update.fallback_models
                else []
            ),
            json.dumps(
                config_update.cost_limits.dict(exclude_none=True)
                if config_update.cost_limits
                else {}
            ),
            json.dumps(config_update.feature_flags.dict() if config_update.feature_flags else {}),
        )

        # Fetch the created config
        current_config = await db.fetch_one(
            "SELECT * FROM app_model_configs WHERE id = $1", config_id
        )

        # Invalidate cache and return new config
        from shared.app_config_cache import get_app_config_cache
        from shared.json_utils import parse_model_config_field

        cache = await get_app_config_cache()
        await cache.invalidate_model_config(app_id)

        # Parse JSONB fields properly before returning
        config_dict = dict(current_config)

        # Parse fallback_models - ensure it's a list
        fallback_models = parse_model_config_field(config_dict, "fallback_models")
        if isinstance(fallback_models, dict):
            fallback_models = []  # Default to empty list if dict

        parsed_config = {
            "id": config_dict["id"],
            "app_id": str(config_dict["app_id"]),  # Convert UUID to string
            "primary_provider": config_dict["primary_provider"],
            "primary_model_id": config_dict["primary_model_id"],
            "primary_parameters": parse_model_config_field(config_dict, "primary_parameters"),
            "fallback_models": fallback_models,
            "cost_limits": parse_model_config_field(config_dict, "cost_limits"),
            "feature_flags": parse_model_config_field(config_dict, "feature_flags"),
            "created_at": config_dict["created_at"],
            "updated_at": config_dict["updated_at"],
        }

        return AppModelConfig(**parsed_config)

    # Build update query dynamically
    update_fields = []
    update_values = []
    param_count = 1

    if config_update.primary_provider is not None:
        update_fields.append(f"primary_provider = ${param_count}")
        update_values.append(config_update.primary_provider.value)
        param_count += 1

    if config_update.primary_model_id is not None:
        update_fields.append(f"primary_model_id = ${param_count}")
        update_values.append(config_update.primary_model_id)
        param_count += 1

    if config_update.primary_parameters is not None:
        update_fields.append(f"primary_parameters = ${param_count}::jsonb")
        update_values.append(json.dumps(config_update.primary_parameters.dict(exclude_none=True)))
        param_count += 1

    if config_update.fallback_models is not None:
        update_fields.append(f"fallback_models = ${param_count}::jsonb")
        update_values.append(
            json.dumps(
                [
                    {**model.dict(exclude_none=True), "provider": model.provider.value}
                    for model in config_update.fallback_models
                ]
            )
        )
        param_count += 1

    if config_update.cost_limits is not None:
        update_fields.append(f"cost_limits = ${param_count}::jsonb")
        update_values.append(json.dumps(config_update.cost_limits.dict(exclude_none=True)))
        param_count += 1

    if config_update.feature_flags is not None:
        update_fields.append(f"feature_flags = ${param_count}::jsonb")
        update_values.append(json.dumps(config_update.feature_flags.dict()))
        param_count += 1

    if not update_fields:
        # Return current config if no updates
        return AppModelConfig(**current_config)

    # Add updated_at field
    update_fields.append(f"updated_at = ${param_count}")
    update_values.append(datetime.utcnow())
    param_count += 1

    # Add app_id for WHERE clause
    update_values.append(app_id)

    query = f"""
        UPDATE app_model_configs
        SET {', '.join(update_fields)}
        WHERE app_id = ${param_count}
        RETURNING *
    """

    updated_config = await db.fetch_one(query, *update_values)

    # Invalidate cache after successful update
    from shared.app_config_cache import get_app_config_cache
    from shared.json_utils import parse_model_config_field

    cache = await get_app_config_cache()
    await cache.invalidate_model_config(app_id)

    # Parse JSONB fields properly before returning
    config_dict = dict(updated_config)

    # Parse fallback_models - ensure it's a list
    fallback_models = parse_model_config_field(config_dict, "fallback_models")
    if isinstance(fallback_models, dict):
        fallback_models = []  # Default to empty list if dict

    parsed_config = {
        "id": config_dict["id"],
        "app_id": str(config_dict["app_id"]),  # Convert UUID to string
        "primary_provider": config_dict["primary_provider"],
        "primary_model_id": config_dict["primary_model_id"],
        "primary_parameters": parse_model_config_field(config_dict, "primary_parameters"),
        "fallback_models": fallback_models,
        "cost_limits": parse_model_config_field(config_dict, "cost_limits"),
        "feature_flags": parse_model_config_field(config_dict, "feature_flags"),
        "created_at": config_dict["created_at"],
        "updated_at": config_dict["updated_at"],
    }

    return AppModelConfig(**parsed_config)


@llm_router.post("/usage", status_code=status.HTTP_201_CREATED)
async def log_llm_usage(usage: LLMUsageLogCreate, db: Database = Depends(get_db)):
    """Log LLM usage for analytics and cost tracking"""
    import json
    from datetime import date

    from shared.llm_pricing import calculate_llm_cost, validate_token_counts

    # Validate token counts
    if not validate_token_counts(usage.prompt_tokens, usage.completion_tokens, usage.total_tokens):
        raise HTTPException(status_code=400, detail="Invalid token counts")

    # Verify app exists and get UUID (handle both UUID and slug)
    try:
        # Try as UUID first
        app_uuid = UUID(usage.app_id)
        app = await db.fetch_one("SELECT id FROM apps WHERE id = $1", app_uuid)
    except ValueError:
        # If not UUID, treat as slug
        app = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", usage.app_id)

    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Use the actual app UUID for database operations
    app_uuid = app["id"]

    # Verify user exists
    user = await db.fetch_one("SELECT id FROM users WHERE id = $1", usage.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Calculate cost server-side (SECURITY: never trust client-provided costs)
    try:
        calculated_cost = calculate_llm_cost(
            provider=usage.provider.value,
            model_id=usage.model_id,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cost calculation failed: {str(e)}")

    # Insert usage log
    usage_id = uuid4()
    await db.execute(
        """
        INSERT INTO llm_usage_logs (
            id, user_id, app_id, provider, model_id,
            prompt_tokens, completion_tokens, total_tokens,
            cost_usd, latency_ms, prompt_hash, finish_reason,
            was_fallback, fallback_reason, request_metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb)
    """,
        usage_id,
        usage.user_id,
        app_uuid,
        usage.provider.value,
        usage.model_id,
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
        calculated_cost,
        usage.latency_ms,
        usage.prompt_hash,
        usage.finish_reason,
        usage.was_fallback,
        usage.fallback_reason,
        json.dumps(usage.request_metadata),
    )

    # Update daily cost tracking (upsert)
    today = date.today()
    month = today.strftime("%Y-%m")

    await db.execute(
        """
        INSERT INTO llm_cost_tracking (
            user_id, app_id, tracking_date, tracking_month,
            total_requests, total_tokens, total_cost_usd, model_usage
        ) VALUES ($1, $2, $3, $4, 1, $5, $6, $7::jsonb)
        ON CONFLICT (user_id, app_id, tracking_date)
        DO UPDATE SET
            total_requests = llm_cost_tracking.total_requests + 1,
            total_tokens = llm_cost_tracking.total_tokens + $5,
            total_cost_usd = llm_cost_tracking.total_cost_usd + $6,
            model_usage = COALESCE(llm_cost_tracking.model_usage, '{}'::jsonb) || $7::jsonb,
            updated_at = CURRENT_TIMESTAMP
    """,
        usage.user_id,
        app_uuid,
        today,
        month,
        usage.total_tokens,
        calculated_cost,
        json.dumps({usage.model_id: {"requests": 1, "cost": float(calculated_cost)}}),
    )

    return {
        "message": "Usage logged successfully",
        "usage_id": usage_id,
        "calculated_cost_usd": calculated_cost,
    }


@llm_router.get("/cost-estimate")
async def estimate_llm_cost(
    provider: str = Query(..., description="LLM provider (anthropic, openai)"),
    model_id: str = Query(..., description="Model identifier"),
    estimated_tokens: int = Query(..., ge=1, le=1000000, description="Estimated total tokens"),
):
    """Estimate LLM cost for a given token count"""
    from shared.llm_pricing import estimate_cost_range, get_model_pricing

    try:
        # Get cost range estimation
        cost_range = estimate_cost_range(provider, model_id, estimated_tokens)

        # Get model pricing details
        pricing = get_model_pricing(provider, model_id)

        return {
            "provider": provider,
            "model_id": model_id,
            "estimated_tokens": estimated_tokens,
            "cost_range": cost_range,
            "pricing_per_million_tokens": pricing,
            "note": "Actual cost depends on input/output token ratio",
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cost estimation failed: {str(e)}")


@llm_router.get("/supported-models")
async def get_supported_models():
    """Get list of all supported LLM models and their pricing"""
    from shared.llm_pricing import PRICING_CONFIG, get_all_supported_models

    models = get_all_supported_models()

    # Add pricing info to response
    models_with_pricing = {}
    for provider, model_list in models.items():
        models_with_pricing[provider] = {}
        for model_id in model_list:
            models_with_pricing[provider][model_id] = PRICING_CONFIG[provider][model_id]

    return {
        "supported_models": models_with_pricing,
        "note": "Pricing is per million tokens (input/output)",
    }


@llm_router.get("/users/{user_id}/usage", response_model=LLMUsageStats)
async def get_user_llm_usage(
    user_id: UUID,
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    app_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get LLM usage statistics for a user"""
    from datetime import timedelta

    # Users can only see their own stats unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Build query conditions
    conditions = ["user_id = $1", "created_at >= $2", "created_at <= $3"]
    params = [user_id, start_date, end_date]

    if app_id:
        conditions.append("app_id = $4")
        params.append(app_id)

    where_clause = " AND ".join(conditions)

    # Get aggregate stats
    stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_requests,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as average_latency_ms
        FROM llm_usage_logs
        WHERE {where_clause}
    """,
        *params,
    )

    # Get model breakdown
    model_stats = await db.fetch_all(
        f"""
        SELECT
            provider,
            model_id,
            COUNT(*) as requests,
            SUM(total_tokens) as tokens,
            SUM(cost_usd) as cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage_logs
        WHERE {where_clause}
        GROUP BY provider, model_id
        ORDER BY cost DESC
    """,
        *params,
    )

    # Format model breakdown
    model_breakdown = {}
    for stat in model_stats:
        key = f"{stat['provider']}/{stat['model_id']}"
        model_breakdown[key] = {
            "requests": stat["requests"],
            "tokens": stat["tokens"],
            "cost": float(stat["cost"]),
            "avg_latency": float(stat["avg_latency"]),
        }

    return LLMUsageStats(
        total_requests=stats["total_requests"] or 0,
        total_tokens=stats["total_tokens"] or 0,
        total_cost_usd=float(stats["total_cost_usd"] or 0),
        average_latency_ms=float(stats["average_latency_ms"] or 0),
        model_breakdown=model_breakdown,
        period_start=start_date,
        period_end=end_date,
    )


# Action-based DUST pricing endpoints
@app_router.get("/pricing/actions")
async def get_action_pricing(
    db: Database = Depends(get_db),
):
    """
    Get action-based DUST pricing for mobile app.
    Returns pricing for all active action slugs with caching headers.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info("🎯 Mobile pricing endpoint called: /apps/pricing/actions")

    try:
        # Get all active pricing
        pricing_rows = await db.fetch_all(
            """
            SELECT action_slug, dust_cost, description, updated_at
            FROM action_pricing
            WHERE is_active = true
            ORDER BY action_slug
            """
        )

        # Format response as expected by mobile app
        pricing_data = {}
        for row in pricing_rows:
            pricing_data[row["action_slug"]] = {
                "dust": row["dust_cost"],
                "description": row["description"],
                "last_updated": row["updated_at"].isoformat() + "Z",
            }

        logger.info(f"🎯 Returning {len(pricing_data)} pricing entries to mobile app")
        logger.info(f"🎯 Pricing data: {pricing_data}")
        return pricing_data

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching action pricing: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to retrieve pricing",
                "code": "PRICING_UNAVAILABLE",
                "message": "Pricing service temporarily unavailable",
            },
        )


@app_router.get("/pricing/health")
async def get_pricing_health():
    """
    Health check for pricing service.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info("🎯 Pricing health check called: /apps/pricing/health")

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "endpoint": "/apps/pricing/health",
    }


# Admin endpoints for app management
@admin_router.get("/apps/api")
async def get_apps_api(
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Get apps list as JSON for React app (admin only)"""
    # Calculate offset
    offset = (page - 1) * limit

    # Build query with optional status filter
    base_query = """
        SELECT a.*, u.fairyname as builder_name, u.email as builder_email,
               amc.primary_model_id, amc.primary_provider
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        LEFT JOIN app_model_configs amc ON amc.app_id::uuid = a.id
    """
    count_query = "SELECT COUNT(*) as total FROM apps a"

    params = []
    where_clause = ""

    if status and status != "all":
        where_clause = " WHERE a.status = $1"
        params.append(status)

    # Get total count
    total_result = await db.fetch_one(f"{count_query}{where_clause}", *params)
    total = total_result["total"]

    # Get apps with pagination
    apps = await db.fetch_all(
        f"{base_query}{where_clause} ORDER BY a.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
        *params,
        limit,
        offset,
    )

    # Calculate pages
    pages = (total + limit - 1) // limit

    return {
        "apps": [dict(app) for app in apps],
        "total": total,
        "pages": pages,
        "current_page": page,
        "limit": limit,
    }


@admin_router.patch("/apps/{app_id}/status")
async def update_app_status_api(
    app_id: str,
    status_data: dict,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Update app status via API for React app (admin only)"""
    status = status_data.get("status")

    if status not in ["approved", "pending", "rejected", "suspended"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    # Update the app status
    is_active = status in ["approved"]
    await db.execute(
        """
        UPDATE apps
        SET status = $1, is_active = $2, admin_notes = $3, updated_at = CURRENT_TIMESTAMP
        WHERE id = $4
        """,
        status,
        is_active,
        f"Status changed to {status} by {admin_user.fairyname}",
        app_id,
    )

    # Return updated app
    app = await db.fetch_one(
        """
        SELECT a.*, u.fairyname as builder_name, u.email as builder_email,
               amc.primary_model_id, amc.primary_provider
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        LEFT JOIN app_model_configs amc ON amc.app_id::uuid = a.id
        WHERE a.id = $1
        """,
        app_id,
    )

    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    return dict(app)


@admin_router.delete("/apps/{app_id}")
async def delete_app_api(
    app_id: str,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Delete app via API for React app (admin only)"""
    # Check if app exists
    app = await db.fetch_one("SELECT id, name FROM apps WHERE id = $1", app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Delete the app
    await db.execute("DELETE FROM apps WHERE id = $1", app_id)

    return {"message": f"App '{app['name']}' deleted successfully"}


@admin_router.post("/apps/api", status_code=status.HTTP_201_CREATED)
async def create_app_api(
    app_data: dict,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Create app via API for React app (admin only)"""
    try:
        # Extract data
        name = app_data.get("name")
        slug = app_data.get("slug")
        description = app_data.get("description")
        category = app_data.get("category")
        builder_id = app_data.get("builder_id")
        dust_per_use = app_data.get("dust_per_use", 5)
        icon_url = app_data.get("icon_url", "")
        website_url = app_data.get("website_url", "")
        demo_url = app_data.get("demo_url", "")
        callback_url = app_data.get("callback_url", "")

        # Validate required fields
        if not all([name, slug, description, category, builder_id]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Validate builder exists and is a builder
        builder = await db.fetch_one(
            "SELECT id, fairyname FROM users WHERE id = $1 AND is_builder = true", builder_id
        )
        if not builder:
            raise HTTPException(status_code=400, detail="Invalid builder selected")

        # Check if slug already exists
        existing_app = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", slug)
        if existing_app:
            raise HTTPException(status_code=400, detail="App slug already exists")

        # Validate dust_per_use
        if dust_per_use < 1 or dust_per_use > 100:
            raise HTTPException(status_code=400, detail="DUST per use must be between 1 and 100")

        # Create the app
        app_id = uuid4()

        await db.execute(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            app_id,
            UUID(builder_id),
            name,
            slug,
            description,
            icon_url if icon_url else None,
            dust_per_use,
            "approved",  # Apps are auto-approved
            category,
            website_url if website_url else None,
            demo_url if demo_url else None,
            callback_url if callback_url else None,
            True,  # is_active = true for approved apps
            f"Created by admin {admin_user.fairyname}",
        )

        # Return created app
        app = await db.fetch_one(
            """
            SELECT a.*, u.fairyname as builder_name, u.email as builder_email,
                   amc.primary_model_id, amc.primary_provider
            FROM apps a
            JOIN users u ON a.builder_id = u.id
            LEFT JOIN app_model_configs amc ON amc.app_id::uuid = a.id
            WHERE a.id = $1
            """,
            app_id,
        )

        return dict(app)

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error creating app via API: {e}")
        raise HTTPException(status_code=500, detail="Failed to create app")


@admin_router.put("/apps/{app_id}")
async def update_app_api(
    app_id: str,
    app_data: dict,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Update app via API for React app (admin only)"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Log the app update attempt
        logger.info(f"📝 ADMIN_EDIT: User {admin_user.fairyname} updating app {app_id}")
        logger.info(f"📝 ADMIN_EDIT: New app data: {app_data}")

        # Extract data
        name = app_data.get("name")
        slug = app_data.get("slug")
        description = app_data.get("description")
        category = app_data.get("category")
        status = app_data.get("status", "active")

        # Validate required fields
        if not all([name, slug, description, category]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Check if app exists
        existing_app = await db.fetch_one("SELECT id, slug FROM apps WHERE id = $1", app_id)
        if not existing_app:
            raise HTTPException(status_code=404, detail="App not found")

        # Check if slug is taken by another app
        if existing_app["slug"] != slug:
            slug_check = await db.fetch_one(
                "SELECT id FROM apps WHERE slug = $1 AND id != $2", slug, app_id
            )
            if slug_check:
                raise HTTPException(status_code=400, detail="App slug already exists")

        # Convert status to database format
        db_status = "approved" if status == "active" else "pending"
        is_active = status == "active"

        # Update the app
        await db.execute(
            """
            UPDATE apps
            SET name = $1, slug = $2, description = $3, category = $4,
                status = $5, is_active = $6, updated_at = CURRENT_TIMESTAMP
            WHERE id = $7
            """,
            name,
            slug,
            description,
            category,
            db_status,
            is_active,
            app_id,
        )

        # Return updated app
        app = await db.fetch_one(
            """
            SELECT a.*, u.fairyname as builder_name, u.email as builder_email,
                   amc.primary_model_id, amc.primary_provider
            FROM apps a
            JOIN users u ON a.builder_id = u.id
            LEFT JOIN app_model_configs amc ON amc.app_id::uuid = a.id
            WHERE a.id = $1
            """,
            app_id,
        )

        if app:
            logger.info(f"✅ ADMIN_EDIT: Successfully updated app {app_id}")
            logger.info(
                f"✅ ADMIN_EDIT: Updated app details: name={app['name']}, status={app['status']}"
            )

        return dict(app)

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error updating app via API: {e}")
        raise HTTPException(status_code=500, detail="Failed to update app")


@admin_router.get("/apps/builders")
async def get_builders_api(
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Get list of builders for app creation (admin only)"""
    builders = await db.fetch_all(
        "SELECT id, fairyname, email FROM users WHERE is_builder = true ORDER BY fairyname"
    )
    return [dict(builder) for builder in builders]


# Admin endpoints for managing action pricing
@admin_router.get("/pricing/actions")
async def get_admin_action_pricing(
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """
    Get all action pricing (including inactive) for admin management.
    """
    try:
        pricing_rows = await db.fetch_all(
            """
            SELECT action_slug, dust_cost, description, is_active,
                   created_at, updated_at
            FROM action_pricing
            ORDER BY action_slug
            """
        )

        return [dict(row) for row in pricing_rows]

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching admin action pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pricing data")


@admin_router.post("/pricing/actions/{action_slug}")
async def create_action_pricing(
    action_slug: str,
    pricing_data: dict,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """
    Create action pricing. Admin only.
    """
    try:
        dust_cost = pricing_data.get("dust_cost")
        description = pricing_data.get("description")
        is_active = pricing_data.get("is_active", True)

        # Validate input
        if dust_cost is None or dust_cost < 0:
            raise HTTPException(status_code=400, detail="dust_cost must be >= 0")
        if not description or len(description.strip()) == 0:
            raise HTTPException(status_code=400, detail="description is required")

        # Check if action already exists
        existing = await db.fetch_one(
            "SELECT action_slug FROM action_pricing WHERE action_slug = $1", action_slug
        )
        if existing:
            raise HTTPException(status_code=409, detail="Action pricing already exists")

        # Create new action
        await db.execute(
            """
            INSERT INTO action_pricing (action_slug, dust_cost, description, is_active)
            VALUES ($1, $2, $3, $4)
            """,
            action_slug,
            dust_cost,
            description.strip(),
            is_active,
        )

        # Return created pricing
        created_row = await db.fetch_one(
            """
            SELECT action_slug, dust_cost, description, is_active,
                   created_at, updated_at
            FROM action_pricing
            WHERE action_slug = $1
            """,
            action_slug,
        )

        return dict(created_row)

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error creating action pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to create pricing")


@admin_router.put("/pricing/actions/{action_slug}")
async def update_action_pricing(
    action_slug: str,
    pricing_data: dict,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """
    Update action pricing. Admin only.
    """
    try:
        dust_cost = pricing_data.get("dust_cost")
        description = pricing_data.get("description")
        is_active = pricing_data.get("is_active", True)

        # Validate input
        if dust_cost is None or dust_cost < 0:
            raise HTTPException(status_code=400, detail="dust_cost must be >= 0")
        if not description or len(description.strip()) == 0:
            raise HTTPException(status_code=400, detail="description is required")

        # Update pricing
        result = await db.execute(
            """
            UPDATE action_pricing
            SET dust_cost = $1, description = $2, is_active = $3,
                updated_at = CURRENT_TIMESTAMP
            WHERE action_slug = $4
            """,
            dust_cost,
            description.strip(),
            is_active,
            action_slug,
        )

        if "UPDATE 0" in result:
            # Create new action if it doesn't exist
            await db.execute(
                """
                INSERT INTO action_pricing (action_slug, dust_cost, description, is_active)
                VALUES ($1, $2, $3, $4)
                """,
                action_slug,
                dust_cost,
                description.strip(),
                is_active,
            )

        # Return updated pricing
        updated_row = await db.fetch_one(
            """
            SELECT action_slug, dust_cost, description, is_active,
                   created_at, updated_at
            FROM action_pricing
            WHERE action_slug = $1
            """,
            action_slug,
        )

        return dict(updated_row)

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error updating action pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to update pricing")


@admin_router.delete("/pricing/actions/{action_slug}")
async def delete_action_pricing(
    action_slug: str,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """
    Delete action pricing. Admin only.
    """
    try:
        result = await db.execute("DELETE FROM action_pricing WHERE action_slug = $1", action_slug)

        if "DELETE 0" in result:
            raise HTTPException(status_code=404, detail="Action pricing not found")

        return {"message": f"Action pricing for '{action_slug}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting action pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete pricing")


# ============================================================================
# REFERRAL ROUTES
# ============================================================================

@referral_router.post("/validate", response_model=ReferralValidateResponse)
async def validate_referral_code(
    request: ReferralValidateRequest,
    db: Database = Depends(get_db),
):
    """Validate referral code during DUST claiming"""
    # Get referral code details with user info
    code_data = await db.fetch_one(
        """
        SELECT rc.*, u.fairyname 
        FROM referral_codes rc
        JOIN users u ON rc.user_id = u.id
        WHERE rc.referral_code = $1
        """,
        request.referral_code,
    )

    # Default bonus amounts (will be configurable via admin later)
    referee_bonus = 15
    referrer_bonus = 15

    if not code_data:
        return ReferralValidateResponse(
            valid=False,
            expired=False,
            referee_bonus=referee_bonus,
            referrer_bonus=referrer_bonus,
        )

    # Check if code is expired
    from datetime import timezone
    now = datetime.now(timezone.utc)
    is_expired = code_data["expires_at"] < now
    is_active = code_data["is_active"]

    if not is_active or is_expired:
        return ReferralValidateResponse(
            valid=False,
            expired=is_expired,
            referee_bonus=referee_bonus,
            referrer_bonus=referrer_bonus,
        )

    return ReferralValidateResponse(
        valid=True,
        expired=False,
        referrer_user_id=code_data["user_id"],
        referrer_name=code_data["fairyname"],
        referee_bonus=referee_bonus,
        referrer_bonus=referrer_bonus,
    )


@referral_router.post("/complete", response_model=ReferralCompleteResponse)
async def complete_referral(
    request: ReferralCompleteRequest,
    current_user: TokenData = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Database = Depends(get_db),
):
    """Complete referral when code is redeemed"""
    # Validate referral code exists and is active
    code_data = await db.fetch_one(
        """
        SELECT rc.*, u.fairyname 
        FROM referral_codes rc
        JOIN users u ON rc.user_id = u.id
        WHERE rc.referral_code = $1 AND rc.is_active = true AND rc.expires_at > CURRENT_TIMESTAMP
        """,
        request.referral_code,
    )

    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid or expired referral code")

    referrer_user_id = code_data["user_id"]

    # Check if referee is trying to use their own code
    if str(referrer_user_id) == str(request.referee_user_id):
        raise HTTPException(status_code=400, detail="Cannot use your own referral code")

    # Check if referee has already used any referral code (with better duplicate detection)
    existing_redemption = await db.fetch_one(
        """SELECT id FROM referral_redemptions 
           WHERE referee_user_id = $1 OR 
                 (referral_code = $2 AND referee_user_id = $1)""",
        request.referee_user_id,
        request.referral_code,
    )

    if existing_redemption:
        print(f"🚫 REFERRAL_DUPLICATE: User {request.referee_user_id} already used referral code {request.referral_code}", flush=True)
        raise HTTPException(status_code=400, detail="You have already used a referral code")

    # Check referrer hasn't exceeded max referrals (100 for now, configurable later)
    referral_count = await db.fetch_one(
        "SELECT COUNT(*) as count FROM referral_redemptions WHERE referrer_user_id = $1",
        referrer_user_id,
    )

    max_referrals = 100  # Configurable via admin later
    if referral_count["count"] >= max_referrals:
        raise HTTPException(status_code=400, detail="Referrer has reached maximum referral limit")

    # Default bonus amounts (configurable via admin later)
    referee_bonus = 15
    referrer_bonus = 15

    # Check for milestone bonus
    milestone_bonus = 0
    current_referrals = referral_count["count"] + 1  # After this redemption

    # Milestone rewards: 5 referrals = 25 DUST, 10 referrals = 50 DUST
    milestone_thresholds = {5: 25, 10: 50}
    if current_referrals in milestone_thresholds:
        milestone_bonus = milestone_thresholds[current_referrals]

    # Check one more time if this specific redemption already exists (prevent race condition)
    existing_specific = await db.fetch_one(
        """SELECT id FROM referral_redemptions 
           WHERE referral_code = $1 AND referee_user_id = $2""",
        request.referral_code,
        request.referee_user_id,
    )
    
    if existing_specific:
        print(f"🚫 REFERRAL_DUPLICATE: Redemption already exists for user {request.referee_user_id} with code {request.referral_code}", flush=True)
        # Return success but don't process again
        return ReferralCompleteResponse(
            success=True,
            referrer_user_id=referrer_user_id,
            referee_bonus_granted=0,  # Already granted
            referrer_bonus_granted=0,  # Already granted
            milestone_bonus=0,
        )

    # Create redemption record with better duplicate protection
    try:
        redemption = await db.fetch_one(
            """
            INSERT INTO referral_redemptions (
                referral_code, referrer_user_id, referee_user_id,
                referee_bonus, referrer_bonus, milestone_bonus
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            request.referral_code,
            referrer_user_id,
            request.referee_user_id,
            referee_bonus,
            referrer_bonus,
            milestone_bonus,
        )
            
        print(f"✅ REFERRAL_CREATED: Redemption record created with ID {redemption['id']}", flush=True)
    except Exception as e:
        print(f"💥 REFERRAL_ERROR: Failed to create redemption record: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to process referral")

    # Grant DUST bonuses via the ledger service
    import httpx
    import os

    environment = os.getenv("ENVIRONMENT", "staging")
    base_url_suffix = "production" if environment == "production" else "staging"
    ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"

    redemption_id = redemption["id"]
    
    try:
        print(f"🎯 REFERRAL_GRANTS: Starting DUST grants for redemption {redemption_id}", flush=True)
        print(f"  - Referee: {request.referee_user_id} gets {referee_bonus} DUST", flush=True)
        print(f"  - Referrer: {referrer_user_id} gets {referrer_bonus} DUST", flush=True)
        print(f"  - Milestone: {milestone_bonus} DUST", flush=True)
        
        async with httpx.AsyncClient() as client:
            # Grant referee bonus
            print(f"💰 REFERRAL_GRANT: Granting referee bonus...", flush=True)
            referee_response = await client.post(
                f"{ledger_url}/grants/referral-reward",
                json={
                    "user_id": str(request.referee_user_id),
                    "amount": referee_bonus,
                    "reason": "referee_bonus",
                    "referral_id": str(redemption_id),
                    "idempotency_key": f"referee_{redemption_id}",
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('SERVICE_JWT_TOKEN', credentials.credentials)}"
                },
                timeout=30.0,
            )
            
            if referee_response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to grant referee bonus: {referee_response.text}"
                )
            print(f"✅ REFERRAL_GRANT: Referee bonus granted successfully", flush=True)

            # Grant referrer bonus
            print(f"💰 REFERRAL_GRANT: Granting referrer bonus...", flush=True)
            referrer_response = await client.post(
                f"{ledger_url}/grants/referral-reward",
                json={
                    "user_id": str(referrer_user_id),
                    "amount": referrer_bonus,
                    "reason": "referral_bonus",
                    "referral_id": str(redemption_id),
                    "idempotency_key": f"referrer_{redemption_id}",
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('SERVICE_JWT_TOKEN', credentials.credentials)}"
                },
                timeout=30.0,
            )
            
            if referrer_response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to grant referrer bonus: {referrer_response.text}"
                )
            print(f"✅ REFERRAL_GRANT: Referrer bonus granted successfully", flush=True)

            # Grant milestone bonus if applicable
            if milestone_bonus > 0:
                print(f"💰 REFERRAL_GRANT: Granting milestone bonus...", flush=True)
                milestone_response = await client.post(
                    f"{ledger_url}/grants/referral-reward",
                    json={
                        "user_id": str(referrer_user_id),
                        "amount": milestone_bonus,
                        "reason": "milestone_bonus",
                        "referral_id": str(redemption_id),
                        "idempotency_key": f"milestone_{redemption_id}",
                    },
                    headers={
                        "Authorization": f"Bearer {credentials.credentials}"
                    },
                    timeout=30.0,
                )
                
                if milestone_response.status_code != 200:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to grant milestone bonus: {milestone_response.text}"
                    )
                print(f"✅ REFERRAL_GRANT: Milestone bonus granted successfully", flush=True)

    except httpx.TimeoutException:
        raise HTTPException(status_code=500, detail="Ledger service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Ledger service error: {str(e)}")

    return ReferralCompleteResponse(
        success=True,
        referrer_user_id=referrer_user_id,
        referee_bonus_granted=referee_bonus,
        referrer_bonus_granted=referrer_bonus,
        milestone_bonus=milestone_bonus,
    )


@referral_router.get("/user/{user_id}", response_model=ReferralStatsResponse)
async def get_user_referral_stats(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get user's referral statistics"""
    if str(current_user.user_id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if user has an active referral code
    has_code = await db.fetch_one(
        """
        SELECT id FROM referral_codes 
        WHERE user_id = $1 AND is_active = true AND expires_at > CURRENT_TIMESTAMP
        """,
        user_id,
    )

    # Get successful referrals count and total DUST earned
    referral_stats = await db.fetch_one(
        """
        SELECT 
            COUNT(*) as successful_referrals,
            COALESCE(SUM(referrer_bonus + milestone_bonus), 0) as total_dust_earned
        FROM referral_redemptions 
        WHERE referrer_user_id = $1
        """,
        user_id,
    )

    successful_referrals = referral_stats["successful_referrals"] or 0
    total_dust_earned = referral_stats["total_dust_earned"] or 0

    # Determine next milestone
    next_milestone = None
    milestones = [5, 10, 20, 50, 100]  # Configurable via admin later
    milestone_rewards = {5: 25, 10: 50, 20: 100, 50: 250, 100: 500}

    for milestone in milestones:
        if successful_referrals < milestone:
            next_milestone = {
                "referral_count": milestone,
                "bonus_amount": milestone_rewards.get(milestone, 0),
            }
            break

    # Get recent referrals (last 5)
    recent_referrals_data = await db.fetch_all(
        """
        SELECT rr.id, u.fairyname as referee_name, rr.redeemed_at, 
               (rr.referrer_bonus + rr.milestone_bonus) as dust_earned
        FROM referral_redemptions rr
        JOIN users u ON rr.referee_user_id = u.id
        WHERE rr.referrer_user_id = $1
        ORDER BY rr.redeemed_at DESC
        LIMIT 5
        """,
        user_id,
    )

    recent_referrals = [
        RecentReferral(
            id=r["id"],
            referee_name=r["referee_name"],
            completed_at=r["redeemed_at"],
            dust_earned=r["dust_earned"],
        )
        for r in recent_referrals_data
    ]

    return ReferralStatsResponse(
        has_referral_code=bool(has_code),
        successful_referrals=successful_referrals,
        total_dust_earned=total_dust_earned,
        next_milestone=next_milestone,
        recent_referrals=recent_referrals,
    )


# ============================================================================
# PROMOTIONAL REFERRAL ROUTES
# ============================================================================


@referral_router.post("/promotional/validate", response_model=PromotionalReferralValidateResponse)
async def validate_promotional_referral_code(
    request: PromotionalReferralValidateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Validate a promotional referral code"""
    # Get promotional code details
    code_data = await db.fetch_one(
        """
        SELECT id, code, description, dust_bonus, max_uses, current_uses, expires_at, is_active
        FROM promotional_referral_codes
        WHERE code = $1
        """,
        request.promotional_code.upper(),
    )

    if not code_data:
        return PromotionalReferralValidateResponse(
            valid=False,
            expired=False,
            max_uses_reached=False,
            already_redeemed=False,
            dust_bonus=0,
            description="",
        )

    # Check if code is expired
    from datetime import timezone
    now = datetime.now(timezone.utc)
    is_expired = code_data["expires_at"] < now
    is_active = code_data["is_active"]

    # Check if max uses reached
    max_uses_reached = False
    if code_data["max_uses"] is not None:
        max_uses_reached = code_data["current_uses"] >= code_data["max_uses"]

    # Check if user already redeemed this code
    already_redeemed = False
    existing_redemption = await db.fetch_one(
        """
        SELECT id FROM promotional_referral_redemptions
        WHERE promotional_code = $1 AND user_id = $2
        """,
        request.promotional_code.upper(),
        current_user.user_id,
    )
    
    if existing_redemption:
        already_redeemed = True

    if not is_active or is_expired or max_uses_reached or already_redeemed:
        return PromotionalReferralValidateResponse(
            valid=False,
            expired=is_expired,
            max_uses_reached=max_uses_reached,
            already_redeemed=already_redeemed,
            dust_bonus=code_data["dust_bonus"],
            description=code_data["description"],
        )

    return PromotionalReferralValidateResponse(
        valid=True,
        expired=False,
        max_uses_reached=False,
        already_redeemed=False,
        dust_bonus=code_data["dust_bonus"],
        description=code_data["description"],
    )


@referral_router.post("/promotional/redeem", response_model=PromotionalReferralRedeemResponse)
async def redeem_promotional_referral_code(
    request: PromotionalReferralRedeemRequest,
    db: Database = Depends(get_db),
):
    """Redeem a promotional referral code for DUST bonus"""
    # Validate promotional code exists and is active
    code_data = await db.fetch_one(
        """
        SELECT id, code, description, dust_bonus, max_uses, current_uses, expires_at, is_active
        FROM promotional_referral_codes
        WHERE code = $1 AND is_active = true
        """,
        request.promotional_code.upper(),
    )

    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid promotional code")

    # Check if code is expired
    from datetime import timezone
    now = datetime.now(timezone.utc)
    if code_data["expires_at"] < now:
        raise HTTPException(status_code=400, detail="Promotional code has expired")

    # Check if max uses reached
    if code_data["max_uses"] is not None and code_data["current_uses"] >= code_data["max_uses"]:
        raise HTTPException(status_code=400, detail="Promotional code has reached maximum uses")

    # Check if user already redeemed this code
    existing_redemption = await db.fetch_one(
        """
        SELECT id FROM promotional_referral_redemptions
        WHERE promotional_code = $1 AND user_id = $2
        """,
        request.promotional_code.upper(),
        request.user_id,
    )
    
    if existing_redemption:
        raise HTTPException(status_code=400, detail="You have already redeemed this promotional code")

    # Start transaction for atomic operations
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Record the redemption
            await conn.execute(
                """
                INSERT INTO promotional_referral_redemptions (
                    promotional_code, user_id, dust_bonus
                ) VALUES ($1, $2, $3)
                """,
                request.promotional_code.upper(),
                request.user_id,
                code_data["dust_bonus"],
            )

            # Update usage count
            await conn.execute(
                """
                UPDATE promotional_referral_codes
                SET current_uses = current_uses + 1
                WHERE id = $1
                """,
                code_data["id"],
            )

            # Grant DUST to user via ledger service
            import httpx
            import os

            environment = os.getenv("ENVIRONMENT", "staging")
            base_url_suffix = "production" if environment == "production" else "staging"
            ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"

            try:
                # Check which token we're using for debugging
                service_token = os.getenv('SERVICE_JWT_TOKEN')
                if not service_token:
                    raise HTTPException(
                        status_code=500,
                        detail="SERVICE_JWT_TOKEN environment variable not configured. Please add it to apps service."
                    )
                
                print(f"🔑 PROMO_REDEEM: Using SERVICE_JWT_TOKEN for ledger auth", flush=True)
                print(f"🔗 PROMO_REDEEM: Calling ledger at {ledger_url}/grants/promotional", flush=True)
                
                async with httpx.AsyncClient() as client:
                    ledger_response = await client.post(
                        f"{ledger_url}/grants/promotional",
                        json={
                            "user_id": str(request.user_id),
                            "amount": code_data["dust_bonus"],
                            "reason": f"Promotional code redemption: {request.promotional_code.upper()}",
                            "promotional_code": request.promotional_code.upper(),
                            "idempotency_key": f"promo_{request.promotional_code.upper()}_{request.user_id}",
                        },
                        headers={
                            "Authorization": f"Bearer {service_token}"
                        },
                        timeout=30.0,
                    )
                    
                    print(f"🏦 LEDGER_RESPONSE: Status {ledger_response.status_code}", flush=True)
                    print(f"🏦 LEDGER_RESPONSE: Body {ledger_response.text[:200]}", flush=True)
                    
                    if ledger_response.status_code != 200:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to grant DUST bonus: Status {ledger_response.status_code}, Body: {ledger_response.text}",
                        )
                    
                    print(f"✅ PROMO_REDEEM: Successfully granted {code_data['dust_bonus']} DUST", flush=True)

            except httpx.TimeoutException as e:
                print(f"⏰ PROMO_REDEEM: Timeout error: {str(e)}", flush=True)
                raise HTTPException(
                    status_code=500,
                    detail="Timeout while granting DUST bonus",
                )
            except httpx.RequestError as e:
                print(f"🌐 PROMO_REDEEM: HTTP request error: {str(e)}", flush=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Network error while granting DUST bonus: {str(e)}",
                )
            except Exception as e:
                print(f"💥 PROMO_REDEEM: Unexpected error: {str(e)}", flush=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to grant DUST bonus: {str(e)}",
                )

    return PromotionalReferralRedeemResponse(
        success=True,
        dust_bonus_granted=code_data["dust_bonus"],
        description=code_data["description"],
    )
