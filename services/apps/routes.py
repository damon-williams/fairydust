# services/apps/routes.py
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, Query, status

from models import (
    App, AppCreate, AppValidation, AppStatus,
    AppModelConfig, AppModelConfigCreate, AppModelConfigUpdate,
    LLMUsageLogCreate, LLMUsageLog, LLMUsageStats
)
from shared.database import get_db, Database
from shared.auth_middleware import get_current_user, require_admin, TokenData

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
    db: Database = Depends(get_db)
):
    """Create a new app (builders only)"""
    app_id = uuid4()
    
    # Insert app into database
    await db.execute("""
        INSERT INTO apps (
            id, builder_id, name, slug, description, icon_url,
            status, category, website_url, demo_url, callback_url, is_active
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    """, 
        app_id, UUID(current_user.user_id), app_data.name, app_data.slug,
        app_data.description, app_data.icon_url,
        AppStatus.APPROVED, app_data.category, app_data.website_url,
        app_data.demo_url, app_data.callback_url, True
    )
    
    # Fetch the created app
    app_result = await db.fetch_one("SELECT * FROM apps WHERE id = $1", app_id)
    return App(**app_result)

@app_router.get("/validate/{app_id}", response_model=AppValidation)
async def validate_app(
    app_id: UUID,
    db: Database = Depends(get_db)
):
    """Validate app for ledger service"""
    app_data = await db.fetch_one("""
        SELECT id, name, builder_id, status, is_active
        FROM apps WHERE id = $1
    """, app_id)
    
    if not app_data:
        return AppValidation(
            app_id=app_id,
            is_valid=False,
            is_active=False,
            dust_per_use=0,
            name="",
            builder_id=UUID("00000000-0000-0000-0000-000000000000")
        )
    
    is_valid = app_data["status"] == AppStatus.APPROVED
    
    return AppValidation(
        app_id=app_id,
        is_valid=is_valid,
        is_active=app_data["is_active"] and is_valid,
        name=app_data["name"],
        builder_id=app_data["builder_id"]
    )

@admin_router.put("/{app_id}/approve")
async def approve_app(
    app_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Approve an app (admin only)"""
    await db.execute("""
        UPDATE apps 
        SET status = $1, is_active = $2, updated_at = $3
        WHERE id = $4
    """, AppStatus.APPROVED, True, datetime.utcnow(), app_id)
    
    return {"message": "App approved", "app_id": app_id}

@marketplace_router.get("/")
async def browse_marketplace(
    db: Database = Depends(get_db)
):
    """Simple marketplace endpoint"""
    apps = await db.fetch_all("""
        SELECT a.*, u.fairyname as builder_fairyname
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        WHERE a.status = $1 AND a.is_active = $2
        ORDER BY a.created_at DESC
        LIMIT 20
    """, AppStatus.APPROVED, True)
    
    return {"apps": apps}

# ============================================================================
# LLM MODEL CONFIGURATION ROUTES
# ============================================================================

llm_router = APIRouter()

@llm_router.get("/{app_id}/model-config", response_model=AppModelConfig)
async def get_app_model_config(
    app_id: str,
    db: Database = Depends(get_db)
):
    """Get LLM model configuration for an app"""
    config = await db.fetch_one("""
        SELECT * FROM app_model_configs WHERE app_id = $1
    """, app_id)
    
    if not config:
        raise HTTPException(
            status_code=404, 
            detail=f"Model configuration not found for app {app_id}"
        )
    
    return AppModelConfig(**config)

@llm_router.put("/{app_id}/model-config", response_model=AppModelConfig)
async def update_app_model_config(
    app_id: str,
    config_update: AppModelConfigUpdate,
    current_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db)
):
    """Update LLM model configuration for an app (admin only)"""
    import json
    
    # Check if app exists
    app = await db.fetch_one("SELECT id FROM apps WHERE id = $1", app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    # Get current config
    current_config = await db.fetch_one(
        "SELECT * FROM app_model_configs WHERE app_id = $1", app_id
    )
    
    if not current_config:
        raise HTTPException(status_code=404, detail="Model configuration not found")
    
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
        update_values.append(json.dumps([
            {**model.dict(exclude_none=True), "provider": model.provider.value}
            for model in config_update.fallback_models
        ]))
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
    return AppModelConfig(**updated_config)

@llm_router.post("/usage", status_code=status.HTTP_201_CREATED)
async def log_llm_usage(
    usage: LLMUsageLogCreate,
    db: Database = Depends(get_db)
):
    """Log LLM usage for analytics and cost tracking"""
    import json
    from datetime import date
    
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
    
    # Insert usage log
    usage_id = uuid4()
    await db.execute("""
        INSERT INTO llm_usage_logs (
            id, user_id, app_id, provider, model_id,
            prompt_tokens, completion_tokens, total_tokens,
            cost_usd, latency_ms, prompt_hash, finish_reason,
            was_fallback, fallback_reason, request_metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb)
    """, 
        usage_id, usage.user_id, app_uuid, usage.provider.value, usage.model_id,
        usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
        usage.cost_usd, usage.latency_ms, usage.prompt_hash, usage.finish_reason,
        usage.was_fallback, usage.fallback_reason, json.dumps(usage.request_metadata)
    )
    
    # Update daily cost tracking (upsert)
    today = date.today()
    month = today.strftime("%Y-%m")
    
    await db.execute("""
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
        usage.user_id, app_uuid, today, month,
        usage.total_tokens, usage.cost_usd,
        json.dumps({usage.model_id: {"requests": 1, "cost": float(usage.cost_usd)}})
    )
    
    return {"message": "Usage logged successfully", "usage_id": usage_id}

@llm_router.get("/users/{user_id}/usage", response_model=LLMUsageStats)
async def get_user_llm_usage(
    user_id: UUID,
    period: str = Query("daily", regex="^(daily|monthly)$"),
    app_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
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
    stats = await db.fetch_one(f"""
        SELECT 
            COUNT(*) as total_requests,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as average_latency_ms
        FROM llm_usage_logs
        WHERE {where_clause}
    """, *params)
    
    # Get model breakdown
    model_stats = await db.fetch_all(f"""
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
    """, *params)
    
    # Format model breakdown
    model_breakdown = {}
    for stat in model_stats:
        key = f"{stat['provider']}/{stat['model_id']}"
        model_breakdown[key] = {
            "requests": stat["requests"],
            "tokens": stat["tokens"],
            "cost": float(stat["cost"]),
            "avg_latency": float(stat["avg_latency"])
        }
    
    return LLMUsageStats(
        total_requests=stats["total_requests"] or 0,
        total_tokens=stats["total_tokens"] or 0,
        total_cost_usd=float(stats["total_cost_usd"] or 0),
        average_latency_ms=float(stats["average_latency_ms"] or 0),
        model_breakdown=model_breakdown,
        period_start=start_date,
        period_end=end_date
    )