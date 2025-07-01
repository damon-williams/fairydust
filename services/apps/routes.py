# services/apps/routes.py
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from models import (
    App,
    AppCreate,
    AppModelConfig,
    AppModelConfigUpdate,
    AppStatus,
    AppValidation,
    LLMUsageLogCreate,
    LLMUsageStats,
)

from shared.auth_middleware import TokenData, get_current_user, require_admin
from shared.database import Database, get_db

# Create routers
app_router = APIRouter()
admin_router = APIRouter()
marketplace_router = APIRouter()

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
            dust_per_use=0,
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
            json.dumps(config_update.primary_parameters.dict(exclude_none=True) if config_update.primary_parameters else {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}),
            json.dumps([model.dict(exclude_none=True) for model in config_update.fallback_models] if config_update.fallback_models else []),
            json.dumps(config_update.cost_limits.dict(exclude_none=True) if config_update.cost_limits else {}),
            json.dumps(config_update.feature_flags.dict() if config_update.feature_flags else {}),
        )
        
        # Fetch the created config
        current_config = await db.fetch_one("SELECT * FROM app_model_configs WHERE id = $1", config_id)
        
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
                "message": "Pricing service temporarily unavailable"
            }
        )


@app_router.get("/pricing/health")
async def get_pricing_health():
    """
    Health check for pricing service.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


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
            dust_cost, description.strip(), is_active, action_slug
        )

        if "UPDATE 0" in result:
            # Create new action if it doesn't exist
            await db.execute(
                """
                INSERT INTO action_pricing (action_slug, dust_cost, description, is_active)
                VALUES ($1, $2, $3, $4)
                """,
                action_slug, dust_cost, description.strip(), is_active
            )

        # Return updated pricing
        updated_row = await db.fetch_one(
            """
            SELECT action_slug, dust_cost, description, is_active, 
                   created_at, updated_at
            FROM action_pricing 
            WHERE action_slug = $1
            """,
            action_slug
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
        result = await db.execute(
            "DELETE FROM action_pricing WHERE action_slug = $1",
            action_slug
        )

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
