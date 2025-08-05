from auth import get_current_admin_user
from fastapi import APIRouter, Depends

from shared.database import Database, get_db

ai_router = APIRouter()


@ai_router.get("/usage")
async def get_ai_usage_metrics(
    timeframe: str = "7d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get AI usage metrics for all model types (Text, Image, Video)"""

    # Map timeframe to SQL interval
    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
    interval = interval_map.get(timeframe, "7 days")

    # Get text/LLM model stats from ai_usage_logs
    text_stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_requests,
            SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)) as total_tokens,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as avg_latency_ms
        FROM ai_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        AND model_type = 'text'
        """
    )

    # Get image usage stats from ai_usage_logs
    image_stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_images,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as avg_latency_ms
        FROM ai_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        AND model_type = 'image'
        """
    )

    # Get video usage stats from ai_usage_logs
    video_stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_videos,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as avg_latency_ms
        FROM ai_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        AND model_type = 'video'
        """
    )

    # Combine stats (convert Decimal to float for JSON serialization)
    total_stats = {
        "total_requests": (text_stats["total_requests"] if text_stats else 0) + 
                         (image_stats["total_images"] if image_stats else 0) + 
                         (video_stats["total_videos"] if video_stats else 0),
        "total_tokens": (text_stats["total_tokens"] if text_stats else 0),
        "total_images": (image_stats["total_images"] if image_stats else 0),
        "total_videos": (video_stats["total_videos"] if video_stats else 0),
        "total_cost_usd": (
            float(text_stats["total_cost_usd"] if text_stats and text_stats["total_cost_usd"] else 0)
            + float(image_stats["total_cost_usd"] if image_stats and image_stats["total_cost_usd"] else 0)
            + float(video_stats["total_cost_usd"] if video_stats and video_stats["total_cost_usd"] else 0)
        ),
        "avg_latency_ms": float(text_stats["avg_latency_ms"] if text_stats and text_stats["avg_latency_ms"] else 0),
    }

    # Get model breakdown for all model types from ai_usage_logs
    all_model_stats = await db.fetch_all(
        f"""
        SELECT
            provider,
            model_id,
            model_type,
            COUNT(*) as requests,
            SUM(cost_usd) as cost,
            AVG(latency_ms) as avg_latency,
            SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)) as tokens,
            SUM(CASE WHEN model_type = 'image' THEN images_generated ELSE 0 END) as images,
            SUM(CASE WHEN model_type = 'video' THEN videos_generated ELSE 0 END) as videos
        FROM ai_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY provider, model_id, model_type
        ORDER BY cost DESC
        LIMIT 15
        """
    )

    # Get per-app usage analytics from ai_usage_logs
    app_usage_stats = await db.fetch_all(
        f"""
        SELECT
            a.name as app_name,
            a.slug as app_slug,
            COUNT(l.id) as total_requests,
            AVG(COALESCE(l.prompt_tokens, 0)) as avg_prompt_tokens,
            AVG(COALESCE(l.completion_tokens, 0)) as avg_completion_tokens,
            AVG(COALESCE(l.prompt_tokens, 0) + COALESCE(l.completion_tokens, 0)) as avg_total_tokens,
            SUM(CASE WHEN l.model_type = 'image' THEN l.images_generated ELSE 0 END) as total_images,
            SUM(CASE WHEN l.model_type = 'video' THEN l.videos_generated ELSE 0 END) as total_videos,
            AVG(l.cost_usd) as avg_cost_per_request,
            SUM(l.cost_usd) as total_cost
        FROM apps a
        LEFT JOIN ai_usage_logs l ON a.id = l.app_id
            AND l.created_at >= NOW() - INTERVAL '{interval}'
        WHERE l.id IS NOT NULL
        GROUP BY a.id, a.name, a.slug
        ORDER BY total_cost DESC
        """
    )

    # Format app usage with models_used array
    formatted_app_usage = []
    for app in app_usage_stats:
        # Get models used by this app from ai_usage_logs
        models_used = await db.fetch_all(
            f"""
            SELECT DISTINCT
                model_id,
                model_type,
                COUNT(*) as requests,
                SUM(cost_usd) as cost,
                AVG(latency_ms) as avg_latency_ms
            FROM ai_usage_logs
            WHERE app_id = (SELECT id FROM apps WHERE slug = $1)
                AND created_at >= NOW() - INTERVAL '{interval}'
            GROUP BY model_id, model_type
            ORDER BY cost DESC
            """,
            app["app_slug"],
        )

        # Convert Decimal types to float for JSON serialization
        app_dict = dict(app)
        for key in [
            "avg_prompt_tokens",
            "avg_completion_tokens",
            "avg_total_tokens",
            "avg_cost_per_request",
            "total_cost",
        ]:
            if app_dict.get(key) is not None:
                app_dict[key] = float(app_dict[key])

        # Convert model data Decimal types to float
        models_dict = []
        for model in models_used:
            model_dict = dict(model)
            for key in ["cost", "avg_latency_ms"]:
                if model_dict.get(key) is not None:
                    model_dict[key] = float(model_dict[key])
            models_dict.append(model_dict)

        formatted_app_usage.append({**app_dict, "models_used": models_dict})

    # Convert model breakdown Decimal types to float
    model_breakdown = []
    for row in all_model_stats:
        row_dict = dict(row)
        for key in ["cost", "avg_latency"]:
            if row_dict.get(key) is not None:
                row_dict[key] = float(row_dict[key])
        model_breakdown.append(row_dict)

    return {
        "timeframe": timeframe,
        "total_stats": total_stats,
        "model_breakdown": model_breakdown,
        "app_usage": formatted_app_usage,
    }


@ai_router.get("/model-usage")
async def get_ai_model_usage(
    type: str = "all",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get model usage statistics for all AI model types"""

    models = []

    # Get models based on type filter
    if type == "all":
        model_types = ["text", "image", "video"]
    else:
        model_types = [type]

    for model_type in model_types:
        type_models = await db.fetch_all(
            """
            SELECT
                CONCAT(provider, '/', model_id) as model,
                model_type,
                provider,
                COUNT(*) as requests,
                SUM(cost_usd) as cost,
                AVG(latency_ms) as avg_latency
            FROM ai_usage_logs
            WHERE created_at >= NOW() - INTERVAL '30 days'
            AND model_type = $1
            GROUP BY provider, model_id, model_type
            ORDER BY cost DESC
            LIMIT 20
            """,
            model_type
        )
        models.extend([dict(row) for row in type_models])

    return models


@ai_router.get("/action-analytics")
async def get_ai_action_analytics(
    timeframe: str = "7d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get AI usage analytics by action-slug for all model types"""

    # Map timeframe to SQL interval
    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
    interval = interval_map.get(timeframe, "7 days")

    # Get action-level analytics from all model types
    action_stats = await db.fetch_all(
        f"""
        SELECT
            l.request_metadata->>'action' as action_slug,
            a.name as app_name,
            l.model_type,
            l.model_id,
            COUNT(l.id) as total_requests,
            AVG(l.cost_usd) as avg_cost_per_request,
            SUM(l.cost_usd) as total_cost,
            AVG(COALESCE(l.prompt_tokens, 0) + COALESCE(l.completion_tokens, 0)) as avg_total_tokens,
            SUM(CASE WHEN l.model_type = 'image' THEN l.images_generated ELSE 0 END) as total_images,
            SUM(CASE WHEN l.model_type = 'video' THEN l.videos_generated ELSE 0 END) as total_videos,
            AVG(l.latency_ms) as avg_latency_ms
        FROM ai_usage_logs l
        LEFT JOIN apps a ON l.app_id = a.id
        WHERE l.created_at >= NOW() - INTERVAL '{interval}'
            AND l.request_metadata->>'action' IS NOT NULL
        GROUP BY l.request_metadata->>'action', a.name, l.model_type, l.model_id
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

        formatted_results.append(
            {
                "action_slug": action_slug,
                "app_name": row["app_name"],
                "model_type": row["model_type"],
                "model_id": row["model_id"],
                "total_requests": row["total_requests"],
                "avg_cost_per_request": avg_cost_usd,
                "total_cost": float(row["total_cost"]) if row["total_cost"] else 0,
                "avg_total_tokens": float(row["avg_total_tokens"])
                if row["avg_total_tokens"]
                else 0,
                "total_images": row["total_images"],
                "total_videos": row["total_videos"],
                "avg_latency_ms": float(row["avg_latency_ms"]) if row["avg_latency_ms"] else 0,
                "current_dust_cost": dust_cost,
                "cost_efficiency": cost_efficiency,
                "cost_per_dust": cost_efficiency if cost_efficiency > 0 else None,
            }
        )

    return {
        "timeframe": timeframe,
        "action_analytics": formatted_results,
        "dust_pricing": [dict(row) for row in dust_pricing],
    }


@ai_router.get("/fallback-analytics")
async def get_ai_fallback_analytics(
    timeframe: str = "7d",
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get AI fallback usage analytics and provider reliability metrics for all model types"""

    # Map timeframe to SQL interval
    interval_map = {"1d": "1 day", "7d": "7 days", "30d": "30 days", "90d": "90 days"}
    interval = interval_map.get(timeframe, "7 days")

    # Get overall fallback statistics (currently only text models)
    fallback_stats = await db.fetch_one(
        f"""
        SELECT
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE was_fallback = true) as fallback_requests,
            COUNT(*) FILTER (WHERE was_fallback = false) as primary_requests,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE ROUND(
                    (COUNT(*) FILTER (WHERE was_fallback = true)::numeric / COUNT(*)) * 100, 2
                )
            END as fallback_percentage
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        """
    )

    # Get fallback breakdown by provider and model type
    provider_reliability = await db.fetch_all(
        f"""
        SELECT
            provider,
            'text' as model_type,
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE was_fallback = false) as primary_success,
            COUNT(*) FILTER (WHERE was_fallback = true) as fallback_usage,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE ROUND(
                    (COUNT(*) FILTER (WHERE was_fallback = false)::numeric / COUNT(*)) * 100, 2
                )
            END as reliability_percentage,
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
            'text' as model_type,
            COUNT(*) as occurrences,
            CASE
                WHEN (SELECT COUNT(*) FROM llm_usage_logs
                     WHERE was_fallback = true
                     AND created_at >= NOW() - INTERVAL '{interval}') = 0 THEN 0
                ELSE ROUND((COUNT(*)::numeric /
                    (SELECT COUNT(*) FROM llm_usage_logs
                     WHERE was_fallback = true
                     AND created_at >= NOW() - INTERVAL '{interval}')
                ) * 100, 2)
            END as percentage_of_fallbacks
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
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE ROUND(
                    (COUNT(*) FILTER (WHERE was_fallback = true)::numeric / COUNT(*)) * 100, 2
                )
            END as fallback_rate
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
            CASE
                WHEN COUNT(l.id) = 0 THEN 0
                ELSE ROUND(
                    (COUNT(l.id) FILTER (WHERE l.was_fallback = true)::numeric / COUNT(l.id)) * 100, 2
                )
            END as fallback_percentage,
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
                "fallback_rate": float(row["fallback_rate"]) if row["fallback_rate"] else 0,
            }
            for row in daily_trends
        ],
        "app_fallback_usage": [dict(row) for row in app_fallback_usage],
    }
