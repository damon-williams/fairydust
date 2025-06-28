import json
from uuid import UUID

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException

from shared.database import Database, get_db

llm_router = APIRouter()


@llm_router.get("/usage")
async def get_llm_usage_metrics(
    timeframe: str = "7d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get LLM usage metrics for React app"""
    
    # Map timeframe to SQL interval
    interval_map = {
        "1d": "1 day",
        "7d": "7 days", 
        "30d": "30 days",
        "90d": "90 days"
    }
    
    interval = interval_map.get(timeframe, "7 days")
    
    # Get total usage stats
    stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_requests,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as avg_latency_ms
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        """
    )

    # Get model breakdown
    model_stats = await db.fetch_all(
        f"""
        SELECT
            provider,
            model_id,
            COUNT(*) as requests,
            SUM(cost_usd) as cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY provider, model_id
        ORDER BY cost DESC
        LIMIT 10
        """
    )

    # Get per-app usage analytics
    app_usage_stats = await db.fetch_all(
        f"""
        SELECT
            a.name as app_name,
            a.slug as app_slug,
            COUNT(l.id) as total_requests,
            AVG(l.prompt_tokens) as avg_prompt_tokens,
            AVG(l.completion_tokens) as avg_completion_tokens,
            AVG(l.total_tokens) as avg_total_tokens,
            AVG(l.cost_usd) as avg_cost_per_request,
            SUM(l.cost_usd) as total_cost,
            AVG(l.latency_ms) as avg_latency_ms
        FROM apps a
        LEFT JOIN llm_usage_logs l ON a.id = l.app_id
            AND l.created_at >= NOW() - INTERVAL '{interval}'
        WHERE l.id IS NOT NULL
        GROUP BY a.id, a.name, a.slug
        ORDER BY total_cost DESC
        """
    )

    return {
        "timeframe": timeframe,
        "total_stats": dict(stats),
        "model_breakdown": [dict(row) for row in model_stats],
        "app_usage": [dict(row) for row in app_usage_stats]
    }


@llm_router.get("/cost-trends")
async def get_llm_cost_trends(
    timeframe: str = "30d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get LLM cost trends over time for React app"""
    
    # Map timeframe to appropriate grouping
    if timeframe in ["1d", "7d"]:
        group_by = "DATE(created_at)"
    else:
        group_by = "DATE_TRUNC('week', created_at)"
    
    interval_map = {
        "1d": "1 day",
        "7d": "7 days",
        "30d": "30 days", 
        "90d": "90 days"
    }
    
    interval = interval_map.get(timeframe, "30 days")
    
    trends = await db.fetch_all(
        f"""
        SELECT
            {group_by} as date,
            SUM(cost_usd) as cost,
            COUNT(*) as requests
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY {group_by}
        ORDER BY date
        """
    )

    return [{"date": row["date"].isoformat(), "cost": float(row["cost"]), "requests": row["requests"]} for row in trends]


@llm_router.get("/model-usage")
async def get_llm_model_usage(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get model usage statistics for React app"""
    
    model_usage = await db.fetch_all(
        """
        SELECT
            CONCAT(provider, '/', model_id) as model,
            COUNT(*) as requests,
            SUM(cost_usd) as cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY provider, model_id
        ORDER BY cost DESC
        LIMIT 20
        """
    )

    return [dict(row) for row in model_usage]


@llm_router.get("/app-configs")
async def get_app_configs(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get app LLM configurations for React app"""
    
    configs = await db.fetch_all(
        """
        SELECT
            a.id as app_id,
            a.name as app_name,
            a.slug as app_slug,
            c.primary_provider,
            c.primary_model_id,
            c.primary_parameters,
            c.fallback_models,
            c.cost_limits,
            c.feature_flags,
            c.updated_at
        FROM apps a
        LEFT JOIN app_model_configs c ON a.id = c.app_id
        ORDER BY a.name
        """
    )

    # Parse JSONB fields
    formatted_configs = []
    for config in configs:
        formatted_config = {
            "app_id": str(config["app_id"]),
            "app_name": config["app_name"],
            "app_slug": config["app_slug"],
            "primary_provider": config["primary_provider"],
            "primary_model_id": config["primary_model_id"],
            "updated_at": config["updated_at"].isoformat() if config["updated_at"] else None
        }
        
        # Parse JSONB fields safely
        for field in ["primary_parameters", "fallback_models", "cost_limits", "feature_flags"]:
            value = config[field]
            if value is not None:
                if isinstance(value, str):
                    try:
                        formatted_config[field] = json.loads(value)
                    except json.JSONDecodeError:
                        formatted_config[field] = None
                else:
                    formatted_config[field] = value
            else:
                formatted_config[field] = None
                
        formatted_configs.append(formatted_config)

    return formatted_configs


@llm_router.put("/app-configs/{app_id}")
async def update_app_config(
    app_id: str,
    config_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update app LLM configuration via JSON API"""
    
    # Verify app exists
    try:
        uuid_app_id = UUID(app_id)
        app = await db.fetch_one("SELECT id, name FROM apps WHERE id = $1", uuid_app_id)
    except (ValueError, TypeError):
        app = await db.fetch_one("SELECT id, name FROM apps WHERE slug = $1", app_id)
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    # Validate and process config data
    try:
        primary_parameters = json.dumps(config_data.get("primary_parameters", {}))
        fallback_models = json.dumps(config_data.get("fallback_models", []))
        cost_limits = json.dumps(config_data.get("cost_limits", {}))
        feature_flags = json.dumps(config_data.get("feature_flags", {}))
        
        # Update configuration
        await db.execute(
            """
            INSERT INTO app_model_configs (
                app_id, primary_provider, primary_model_id, primary_parameters,
                fallback_models, cost_limits, feature_flags, updated_at
            ) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (app_id) DO UPDATE SET
                primary_provider = EXCLUDED.primary_provider,
                primary_model_id = EXCLUDED.primary_model_id,
                primary_parameters = EXCLUDED.primary_parameters,
                fallback_models = EXCLUDED.fallback_models,
                cost_limits = EXCLUDED.cost_limits,
                feature_flags = EXCLUDED.feature_flags,
                updated_at = CURRENT_TIMESTAMP
            """,
            app["id"],
            config_data.get("primary_provider"),
            config_data.get("primary_model_id"),
            primary_parameters,
            fallback_models,
            cost_limits,
            feature_flags
        )
        
        # Invalidate cache
        from shared.app_config_cache import get_app_config_cache
        cache = await get_app_config_cache()
        await cache.invalidate_model_config(str(app["id"]))
        
        return {"success": True, "message": "Configuration updated successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@llm_router.get("/models")
async def get_available_models(
    admin_user: dict = Depends(get_current_admin_user)
):
    """Get available LLM models by provider"""
    
    return {
        "anthropic": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-3-opus-20240229",
        ],
        "openai": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
        ],
    }