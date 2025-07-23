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
    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}

    interval = interval_map.get(timeframe, "7 days")

    # Get total usage stats
    stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_requests,
            SUM(prompt_tokens + completion_tokens) as total_tokens,
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
            AVG(l.prompt_tokens + l.completion_tokens) as avg_total_tokens,
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
        "total_stats": dict(stats) if stats else {},
        "model_breakdown": [dict(row) for row in model_stats],
        "app_usage": [dict(row) for row in app_usage_stats],
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

    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}

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

    return [
        {"date": row["date"].isoformat(), "cost": float(row["cost"]), "requests": row["requests"]}
        for row in trends
    ]


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
            "updated_at": config["updated_at"].isoformat() if config["updated_at"] else None,
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
            feature_flags,
        )

        # Invalidate cache
        from shared.app_config_cache import get_app_config_cache

        cache = await get_app_config_cache()
        await cache.invalidate_model_config(str(app["id"]))

        return {"success": True, "message": "Configuration updated successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@llm_router.get("/action-analytics")
async def get_action_analytics(
    timeframe: str = "7d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get LLM usage analytics by action-slug"""
    
    # Map timeframe to SQL interval
    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
    interval = interval_map.get(timeframe, "7 days")
    
    # Get action-level analytics from request_metadata
    action_stats = await db.fetch_all(
        f"""
        SELECT
            l.request_metadata->>'action' as action_slug,
            a.name as app_name,
            COUNT(l.id) as total_requests,
            AVG(l.cost_usd) as avg_cost_per_request,
            SUM(l.cost_usd) as total_cost,
            AVG(l.prompt_tokens + l.completion_tokens) as avg_total_tokens,
            AVG(l.latency_ms) as avg_latency_ms
        FROM llm_usage_logs l
        LEFT JOIN apps a ON l.app_id = a.id
        WHERE l.created_at >= NOW() - INTERVAL '{interval}'
            AND l.request_metadata->>'action' IS NOT NULL
        GROUP BY l.request_metadata->>'action', a.name
        ORDER BY total_cost DESC
        """
    )
    
    # Get current DUST pricing for comparison
    dust_pricing = await db.fetch_all(
        """
        SELECT action_slug, dust_cost, description, is_active
        FROM action_pricing
        WHERE is_active = true
        ORDER BY action_slug
        """
    )
    
    # Create a mapping of action_slug to dust_cost
    dust_cost_map = {row["action_slug"]: row["dust_cost"] for row in dust_pricing}
    
    # Format results with DUST pricing comparison
    formatted_results = []
    for row in action_stats:
        action_slug = row["action_slug"]
        avg_cost_usd = float(row["avg_cost_per_request"]) if row["avg_cost_per_request"] else 0
        dust_cost = dust_cost_map.get(action_slug, 0)
        
        # Calculate cost efficiency (USD cost per DUST charged)
        cost_efficiency = avg_cost_usd / dust_cost if dust_cost > 0 else 0
        
        formatted_results.append({
            "action_slug": action_slug,
            "app_name": row["app_name"],
            "total_requests": row["total_requests"],
            "avg_cost_per_request": avg_cost_usd,
            "total_cost": float(row["total_cost"]) if row["total_cost"] else 0,
            "avg_total_tokens": float(row["avg_total_tokens"]) if row["avg_total_tokens"] else 0,
            "avg_latency_ms": float(row["avg_latency_ms"]) if row["avg_latency_ms"] else 0,
            "current_dust_cost": dust_cost,
            "cost_efficiency": cost_efficiency,
            "cost_per_dust": cost_efficiency if cost_efficiency > 0 else None
        })
    
    return {
        "timeframe": timeframe,
        "action_analytics": formatted_results,
        "dust_pricing": [dict(row) for row in dust_pricing]
    }


@llm_router.get("/models")
async def get_available_models(admin_user: dict = Depends(get_current_admin_user)):
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


@llm_router.get("/fallback-analytics")
async def get_fallback_analytics(
    timeframe: str = "7d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get LLM fallback usage analytics and provider reliability metrics"""
    
    # Map timeframe to SQL interval
    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
    interval = interval_map.get(timeframe, "7 days")
    
    # Get overall fallback statistics
    fallback_stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE was_fallback = true) as fallback_requests,
            COUNT(*) FILTER (WHERE was_fallback = false) as primary_requests,
            ROUND(
                (COUNT(*) FILTER (WHERE was_fallback = true)::numeric / COUNT(*)) * 100, 2
            ) as fallback_percentage
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        """
    )
    
    # Get fallback breakdown by provider
    provider_reliability = await db.fetch_all(
        f"""
        SELECT
            provider,
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE was_fallback = false) as primary_success,
            COUNT(*) FILTER (WHERE was_fallback = true) as fallback_usage,
            ROUND(
                (COUNT(*) FILTER (WHERE was_fallback = false)::numeric / COUNT(*)) * 100, 2
            ) as reliability_percentage,
            AVG(latency_ms) as avg_latency_ms,
            SUM(cost_usd) as total_cost
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY provider
        ORDER BY total_requests DESC
        """
    )
    
    # Get fallback reasons breakdown
    fallback_reasons = await db.fetch_all(
        f"""
        SELECT
            fallback_reason,
            COUNT(*) as occurrences,
            ROUND((COUNT(*)::numeric / 
                (SELECT COUNT(*) FROM llm_usage_logs 
                 WHERE was_fallback = true 
                 AND created_at >= NOW() - INTERVAL '{interval}')
            ) * 100, 2) as percentage_of_fallbacks
        FROM llm_usage_logs
        WHERE was_fallback = true 
          AND created_at >= NOW() - INTERVAL '{interval}'
          AND fallback_reason IS NOT NULL
        GROUP BY fallback_reason
        ORDER BY occurrences DESC
        """
    )
    
    # Get daily fallback trends
    if timeframe in ["1d", "7d"]:
        group_by = "DATE(created_at)"
        date_format = "%Y-%m-%d"
    else:
        group_by = "DATE_TRUNC('week', created_at)"
        date_format = "%Y-%m-%d"
    
    daily_trends = await db.fetch_all(
        f"""
        SELECT
            {group_by} as date,
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE was_fallback = true) as fallback_requests,
            ROUND(
                (COUNT(*) FILTER (WHERE was_fallback = true)::numeric / COUNT(*)) * 100, 2
            ) as fallback_rate
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY {group_by}
        ORDER BY date
        """
    )
    
    # Get app-specific fallback usage
    app_fallback_usage = await db.fetch_all(
        f"""
        SELECT
            a.name as app_name,
            a.slug as app_slug,
            COUNT(l.id) as total_requests,
            COUNT(l.id) FILTER (WHERE l.was_fallback = true) as fallback_requests,
            ROUND(
                (COUNT(l.id) FILTER (WHERE l.was_fallback = true)::numeric / COUNT(l.id)) * 100, 2
            ) as fallback_percentage,
            AVG(l.cost_usd) as avg_cost_per_request
        FROM apps a
        LEFT JOIN llm_usage_logs l ON a.id = l.app_id
            AND l.created_at >= NOW() - INTERVAL '{interval}'
        WHERE l.id IS NOT NULL
        GROUP BY a.id, a.name, a.slug
        ORDER BY fallback_percentage DESC, total_requests DESC
        """
    )
    
    return {
        "timeframe": timeframe,
        "overall_stats": dict(fallback_stats) if fallback_stats else {},
        "provider_reliability": [dict(row) for row in provider_reliability],
        "fallback_reasons": [dict(row) for row in fallback_reasons],
        "daily_trends": [
            {
                "date": row["date"].strftime(date_format), 
                "total_requests": row["total_requests"],
                "fallback_requests": row["fallback_requests"],
                "fallback_rate": float(row["fallback_rate"]) if row["fallback_rate"] else 0
            }
            for row in daily_trends
        ],
        "app_fallback_usage": [dict(row) for row in app_fallback_usage]
    }
