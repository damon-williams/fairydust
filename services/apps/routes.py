# services/apps/routes.py
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, Query, status

from models import (
    App, AppCreate, AppValidation, AppStatus,
    AppModelConfig, AppModelConfigCreate, AppModelConfigUpdate,
    LLMUsageLogCreate, LLMUsageLog, LLMUsageStats,
    UserRecipe, UserRecipeCreate, UserRecipeUpdate, RecipesResponse,
    LocalRecipe, RecipeSyncRequest, RecipeSyncResponse
)
from shared.database import get_db, Database
from shared.auth_middleware import get_current_user, require_admin, TokenData

# Create routers
app_router = APIRouter()
admin_router = APIRouter()
marketplace_router = APIRouter()
recipe_router = APIRouter()

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
        AppStatus.PENDING, app_data.category, app_data.website_url,
        app_data.demo_url, app_data.callback_url, False
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
    
    # Verify app exists
    app = await db.fetch_one("SELECT id FROM apps WHERE id = $1", usage.app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
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
        usage_id, usage.user_id, usage.app_id, usage.provider.value, usage.model_id,
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
        usage.user_id, usage.app_id, today, month,
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

# ============================================================================
# RECIPE STORAGE ROUTES
# ============================================================================

@recipe_router.get("/users/{user_id}/recipes", response_model=RecipesResponse)
async def get_user_recipes(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    app_id: Optional[str] = Query("fairydust-recipe"),
    favorited_only: bool = Query(False),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get user recipes with pagination and filtering"""
    # Users can only access their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build query conditions
    conditions = ["user_id = $1"]
    params = [user_id]
    param_count = 2
    
    if app_id:
        conditions.append(f"app_id = ${param_count}")
        params.append(app_id)
        param_count += 1
    
    if favorited_only:
        conditions.append(f"is_favorited = ${param_count}")
        params.append(True)
        param_count += 1
    
    where_clause = " AND ".join(conditions)
    
    # Get total count
    count_result = await db.fetch_one(
        f"SELECT COUNT(*) as total FROM user_recipes WHERE {where_clause}",
        *params
    )
    total_count = count_result["total"]
    
    # Get recipes with pagination
    recipes = await db.fetch_all(f"""
        SELECT * FROM user_recipes 
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """, *params, limit, offset)
    
    has_more = (offset + limit) < total_count
    
    return RecipesResponse(
        recipes=[UserRecipe(**recipe) for recipe in recipes],
        total_count=total_count,
        has_more=has_more
    )

@recipe_router.post("/users/{user_id}/recipes", response_model=dict, status_code=status.HTTP_201_CREATED)
async def save_recipe(
    user_id: UUID,
    recipe_data: UserRecipeCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Save a new recipe for the user"""
    # Users can only save to their own account unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    import json
    
    # Validate content size (10MB limit as per spec)
    if len(recipe_data.content.encode('utf-8')) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Recipe content too large (>10MB)")
    
    # Extract title from content if not provided
    title = recipe_data.title
    if not title and recipe_data.content:
        # Try to extract title from first line of content
        first_line = recipe_data.content.split('\n')[0].strip()
        if first_line.startswith('#'):
            title = first_line.lstrip('#').strip()
        elif first_line.startswith('**') and first_line.endswith('**'):
            title = first_line.strip('*').strip()
        else:
            title = first_line[:100] + "..." if len(first_line) > 100 else first_line
    
    recipe_id = uuid4()
    
    # Convert metadata to JSON
    metadata_json = json.dumps(recipe_data.metadata.dict() if recipe_data.metadata else {})
    
    # Insert recipe
    recipe = await db.fetch_one("""
        INSERT INTO user_recipes (
            id, user_id, app_id, title, content, category, metadata, is_favorited
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        RETURNING *
    """, 
        recipe_id, user_id, recipe_data.app_id, title, recipe_data.content,
        recipe_data.category, metadata_json, False
    )
    
    return {"recipe": UserRecipe(**recipe)}

@recipe_router.put("/users/{user_id}/recipes/{recipe_id}", response_model=dict)
async def update_recipe(
    user_id: UUID,
    recipe_id: UUID,
    recipe_update: UserRecipeUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Update recipe (favorite status or title)"""
    # Users can only update their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if recipe exists and belongs to user
    recipe = await db.fetch_one(
        "SELECT * FROM user_recipes WHERE id = $1 AND user_id = $2",
        recipe_id, user_id
    )
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Build update query dynamically
    update_fields = []
    update_values = []
    param_count = 1
    
    if recipe_update.title is not None:
        update_fields.append(f"title = ${param_count}")
        update_values.append(recipe_update.title)
        param_count += 1
    
    if recipe_update.is_favorited is not None:
        update_fields.append(f"is_favorited = ${param_count}")
        update_values.append(recipe_update.is_favorited)
        param_count += 1
    
    if not update_fields:
        # Return current recipe if no updates
        return {"recipe": UserRecipe(**recipe)}
    
    # Add updated_at field
    update_fields.append(f"updated_at = ${param_count}")
    update_values.append(datetime.utcnow())
    param_count += 1
    
    # Add recipe_id and user_id for WHERE clause
    update_values.extend([recipe_id, user_id])
    
    query = f"""
        UPDATE user_recipes 
        SET {', '.join(update_fields)}
        WHERE id = ${param_count} AND user_id = ${param_count + 1}
        RETURNING *
    """
    
    updated_recipe = await db.fetch_one(query, *update_values)
    return {"recipe": UserRecipe(**updated_recipe)}

@recipe_router.delete("/users/{user_id}/recipes/{recipe_id}")
async def delete_recipe(
    user_id: UUID,
    recipe_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Delete a recipe"""
    # Users can only delete their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if recipe exists and belongs to user
    recipe = await db.fetch_one(
        "SELECT id FROM user_recipes WHERE id = $1 AND user_id = $2",
        recipe_id, user_id
    )
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Delete recipe
    await db.execute(
        "DELETE FROM user_recipes WHERE id = $1 AND user_id = $2",
        recipe_id, user_id
    )
    
    return {"success": True, "message": "Recipe deleted successfully"}

@recipe_router.post("/users/{user_id}/recipes/sync", response_model=RecipeSyncResponse)
async def sync_recipes(
    user_id: UUID,
    sync_request: RecipeSyncRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Bulk sync recipes for mobile app"""
    # Users can only sync their own recipes unless admin
    if current_user.user_id != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    import json
    
    sync_timestamp = datetime.utcnow()
    
    # Get server recipes updated after last sync
    server_conditions = ["user_id = $1"]
    server_params = [user_id]
    
    if sync_request.last_sync_timestamp:
        server_conditions.append("updated_at > $2")
        server_params.append(sync_request.last_sync_timestamp)
    
    server_recipes = await db.fetch_all(f"""
        SELECT * FROM user_recipes 
        WHERE {' AND '.join(server_conditions)}
        ORDER BY created_at DESC
    """, *server_params)
    
    # Process local recipes for upload
    sync_conflicts = []
    
    for local_recipe in sync_request.local_recipes:
        # Validate content size
        if len(local_recipe.content.encode('utf-8')) > 10 * 1024 * 1024:
            continue  # Skip recipes that are too large
        
        # Extract title if not provided
        title = local_recipe.title
        if not title and local_recipe.content:
            first_line = local_recipe.content.split('\n')[0].strip()
            if first_line.startswith('#'):
                title = first_line.lstrip('#').strip()
            elif first_line.startswith('**') and first_line.endswith('**'):
                title = first_line.strip('*').strip()
            else:
                title = first_line[:100] + "..." if len(first_line) > 100 else first_line
        
        # Check for conflicts (recipe with same content created around same time)
        # For simplicity, we'll just insert new recipes for now
        # Real conflict resolution would be more complex
        
        recipe_id = uuid4()
        metadata_json = json.dumps(local_recipe.metadata or {})
        
        try:
            await db.execute("""
                INSERT INTO user_recipes (
                    id, user_id, app_id, title, content, category, metadata, 
                    is_favorited, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            """, 
                recipe_id, user_id, local_recipe.app_id, title, local_recipe.content,
                local_recipe.category, metadata_json, False, local_recipe.created_at
            )
        except Exception as e:
            # Log the error but continue with sync
            print(f"Error syncing recipe {local_recipe.local_id}: {e}")
            continue
    
    return RecipeSyncResponse(
        server_recipes=[UserRecipe(**recipe) for recipe in server_recipes],
        sync_conflicts=sync_conflicts,
        sync_timestamp=sync_timestamp
    )