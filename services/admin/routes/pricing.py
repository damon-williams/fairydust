import json
from typing import Any

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException

from shared.database import Database, get_db

pricing_router = APIRouter()


@pricing_router.get("/models")
async def get_model_pricing(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get all model pricing configuration"""
    try:
        # Get pricing from system_config
        pricing_config = await db.fetch_one(
            "SELECT value FROM system_config WHERE key = 'model_pricing'"
        )

        if not pricing_config:
            # Return default pricing structure if not configured
            default_pricing = {
                "anthropic": {
                    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
                    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
                    "claude-3-5-haiku-20241022": {"input": 0.8, "output": 4.0},
                },
                "openai": {
                    "gpt-4o": {"input": 2.5, "output": 10.0},
                    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
                },
                "image": {
                    "black-forest-labs/flux-1.1-pro": {"cost": 0.04},
                    "black-forest-labs/flux-schnell": {"cost": 0.003},
                    "runwayml/gen4-image": {"cost": 0.05},
                },
            }

            # Initialize the database with default pricing
            await db.execute(
                """INSERT INTO system_config (key, value, description, updated_by)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (key) DO NOTHING""",
                "model_pricing",
                json.dumps(default_pricing),
                "AI model pricing configuration (per million tokens for text, per image for image models)",
                admin_user["user_id"],
            )

            return default_pricing

        return json.loads(pricing_config["value"])

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid pricing configuration in database")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load pricing configuration: {str(e)}"
        )


@pricing_router.put("/models")
async def update_model_pricing(
    pricing_data: dict[str, Any],
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update model pricing configuration"""
    try:
        # Validate pricing structure
        valid_providers = {"anthropic", "openai", "image", "video"}

        for provider, models in pricing_data.items():
            if provider not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider '{provider}'. Must be one of: {valid_providers}",
                )

            if not isinstance(models, dict):
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider '{provider}' must contain a dictionary of models",
                )

            for model_id, pricing in models.items():
                if not isinstance(pricing, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Pricing for model '{model_id}' must be a dictionary",
                    )

                # Validate pricing structure based on model type
                if provider in ["anthropic", "openai"]:
                    # Text models need input and output rates
                    if "input" not in pricing or "output" not in pricing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Text model '{model_id}' must have 'input' and 'output' pricing",
                        )
                    if not isinstance(pricing["input"], (int, float)) or not isinstance(
                        pricing["output"], (int, float)
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Text model '{model_id}' pricing must be numeric",
                        )
                    if pricing["input"] < 0 or pricing["output"] < 0:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Text model '{model_id}' pricing must be non-negative",
                        )

                elif provider in ["image", "video"]:
                    # Image/video models need cost per unit
                    if "cost" not in pricing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"{provider.title()} model '{model_id}' must have 'cost' pricing",
                        )
                    if not isinstance(pricing["cost"], (int, float)):
                        raise HTTPException(
                            status_code=400,
                            detail=f"{provider.title()} model '{model_id}' cost must be numeric",
                        )
                    if pricing["cost"] < 0:
                        raise HTTPException(
                            status_code=400,
                            detail=f"{provider.title()} model '{model_id}' cost must be non-negative",
                        )

        # Save to database with versioning and audit trail
        await db.execute(
            """INSERT INTO system_config (key, value, description, updated_by)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (key) DO UPDATE SET
                   value = EXCLUDED.value,
                   description = EXCLUDED.description,
                   updated_by = EXCLUDED.updated_by,
                   updated_at = CURRENT_TIMESTAMP""",
            "model_pricing",
            json.dumps(pricing_data),
            "AI model pricing configuration (per million tokens for text, per image for image models). Changes only apply to future usage.",
            admin_user["user_id"],
        )

        # Create audit log entry for pricing changes
        await db.execute(
            """INSERT INTO system_config (key, value, description, updated_by)
               VALUES ($1, $2, $3, $4)""",
            f"model_pricing_history_{int(__import__('time').time())}",
            json.dumps(
                {
                    "pricing_data": pricing_data,
                    "changed_by": admin_user["fairyname"],
                    "change_timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                    "note": "Pricing changes apply only to future usage calculations",
                }
            ),
            f"Pricing change audit log - effective {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            admin_user["user_id"],
        )

        # Invalidate pricing cache so changes take effect immediately
        from shared.llm_pricing import invalidate_pricing_cache

        invalidate_pricing_cache()

        return {
            "success": True,
            "message": "Model pricing updated successfully. Changes apply only to future usage calculations.",
            "updated_by": admin_user["fairyname"],
            "important_note": "Historical usage costs remain unchanged to preserve financial accuracy.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update pricing configuration: {str(e)}"
        )


@pricing_router.get("/models/{provider}")
async def get_provider_pricing(
    provider: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get pricing for a specific provider"""
    valid_providers = {"anthropic", "openai", "image", "video"}
    if provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{provider}'. Must be one of: {valid_providers}",
        )

    all_pricing = await get_model_pricing(admin_user, db)
    return all_pricing.get(provider, {})


@pricing_router.put("/models/{provider}")
async def update_provider_pricing(
    provider: str,
    provider_pricing: dict[str, Any],
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update pricing for a specific provider"""
    # Get current pricing
    all_pricing = await get_model_pricing(admin_user, db)

    # Update the specific provider
    all_pricing[provider] = provider_pricing

    # Save back to database
    return await update_model_pricing(all_pricing, admin_user, db)


@pricing_router.post("/models/{provider}/{model_id}")
async def add_model_pricing(
    provider: str,
    model_id: str,
    model_pricing: dict[str, Any],
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Add or update pricing for a specific model"""
    # Get current pricing
    all_pricing = await get_model_pricing(admin_user, db)

    # Ensure provider exists
    if provider not in all_pricing:
        all_pricing[provider] = {}

    # Add/update the model
    all_pricing[provider][model_id] = model_pricing

    # Save back to database
    return await update_model_pricing(all_pricing, admin_user, db)


@pricing_router.delete("/models/{provider}/{model_id}")
async def remove_model_pricing(
    provider: str,
    model_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Remove pricing for a specific model"""
    # Get current pricing
    all_pricing = await get_model_pricing(admin_user, db)

    # Check if provider and model exist
    if provider not in all_pricing:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")

    if model_id not in all_pricing[provider]:
        raise HTTPException(
            status_code=404, detail=f"Model '{model_id}' not found in provider '{provider}'"
        )

    # Remove the model
    del all_pricing[provider][model_id]

    # Clean up empty provider
    if not all_pricing[provider]:
        del all_pricing[provider]

    # Save back to database
    await update_model_pricing(all_pricing, admin_user, db)

    return {
        "success": True,
        "message": f"Model '{model_id}' removed from provider '{provider}'",
        "updated_by": admin_user["fairyname"],
    }


@pricing_router.get("/history")
async def get_pricing_history(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get pricing change history for audit purposes"""
    try:
        # Get all pricing history entries
        history_entries = await db.fetch_all(
            """SELECT key, value, description, updated_by, updated_at
               FROM system_config
               WHERE key LIKE 'model_pricing_history_%'
               ORDER BY updated_at DESC
               LIMIT 50"""
        )

        formatted_history = []
        for entry in history_entries:
            try:
                history_data = json.loads(entry["value"])
                formatted_history.append(
                    {
                        "timestamp": entry["updated_at"],
                        "changed_by": history_data.get("changed_by"),
                        "change_timestamp": history_data.get("change_timestamp"),
                        "note": history_data.get("note"),
                        "description": entry["description"],
                        "pricing_snapshot": history_data.get("pricing_data"),
                    }
                )
            except json.JSONDecodeError:
                # Skip malformed entries
                continue

        return {
            "history": formatted_history,
            "note": "Historical pricing data is preserved. Changes only affect future usage calculations.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load pricing history: {str(e)}")


@pricing_router.get("/current-vs-historical")
async def get_pricing_comparison(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Compare current pricing with historical averages for analysis"""
    try:
        current_pricing = await get_model_pricing(admin_user, db)

        # Get the most recent historical pricing for comparison
        latest_history = await db.fetch_one(
            """SELECT value FROM system_config
               WHERE key LIKE 'model_pricing_history_%'
               ORDER BY updated_at DESC
               LIMIT 1"""
        )

        comparison = {
            "current_pricing": current_pricing,
            "has_history": latest_history is not None,
            "note": "All historical usage calculations remain unchanged. Only new usage uses current pricing.",
        }

        if latest_history:
            try:
                history_data = json.loads(latest_history["value"])
                comparison["previous_pricing"] = history_data.get("pricing_data")
                comparison["last_change"] = history_data.get("change_timestamp")
                comparison["changed_by"] = history_data.get("changed_by")
            except json.JSONDecodeError:
                pass

        return comparison

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load pricing comparison: {str(e)}")
