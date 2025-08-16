# services/admin/routes/global_config.py
"""Global configuration endpoints for LLM fallbacks and system defaults"""

from fastapi import APIRouter, Depends, HTTPException, status
from shared.database import Database, get_db
from typing import Dict, List, Any

router = APIRouter()


@router.get("/global-fallbacks")
async def get_global_fallbacks(db: Database = Depends(get_db)) -> Dict[str, Any]:
    """Get global LLM fallback configuration from system_config table"""
    
    try:
        # Fetch global LLM configuration from system_config
        config_rows = await db.fetch_all(
            """
            SELECT key, value 
            FROM system_config 
            WHERE key LIKE 'llm_%'
            ORDER BY key
            """
        )
        
        config = {row["key"]: row["value"] for row in config_rows}
        
        # Parse configuration into response format
        response = {
            "primary_provider": config.get("llm_primary_provider", "anthropic"),
            "primary_model": config.get("llm_primary_model", "claude-3-5-sonnet-20241022"),
            "fallbacks": []
        }
        
        # Parse fallback configurations (llm_fallback_1, llm_fallback_2, etc.)
        fallback_configs = {}
        for key, value in config.items():
            if key.startswith("llm_fallback_"):
                try:
                    parts = key.split("_")
                    if len(parts) >= 4:  # llm_fallback_N_provider or llm_fallback_N_model
                        fallback_num = parts[2]
                        field_type = parts[3]  # provider or model
                        
                        if fallback_num not in fallback_configs:
                            fallback_configs[fallback_num] = {}
                        
                        fallback_configs[fallback_num][field_type] = value
                except Exception:
                    continue
        
        # Convert to sorted list of fallbacks
        for num in sorted(fallback_configs.keys()):
            fallback = fallback_configs[num]
            if "provider" in fallback and "model" in fallback:
                response["fallbacks"].append({
                    "provider": fallback["provider"],
                    "model": fallback["model"]
                })
        
        # If no configuration exists, return safe defaults
        if not response["fallbacks"] and not config:
            response["fallbacks"] = [
                {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                {"provider": "openai", "model": "gpt-4o"}
            ]
        
        return response
        
    except Exception as e:
        # Return emergency defaults if database query fails
        return {
            "primary_provider": "anthropic",
            "primary_model": "claude-3-5-sonnet-20241022",
            "fallbacks": [
                {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                {"provider": "openai", "model": "gpt-4o"}
            ]
        }


@router.post("/global-fallbacks")
async def update_global_fallbacks(
    config: Dict[str, Any],
    db: Database = Depends(get_db)
) -> Dict[str, str]:
    """Update global LLM fallback configuration"""
    
    try:
        # Update primary provider and model
        if "primary_provider" in config:
            await db.execute(
                """
                INSERT INTO system_config (key, value, description)
                VALUES ('llm_primary_provider', $1, 'Primary LLM provider for global fallbacks')
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                config["primary_provider"]
            )
        
        if "primary_model" in config:
            await db.execute(
                """
                INSERT INTO system_config (key, value, description)
                VALUES ('llm_primary_model', $1, 'Primary LLM model for global fallbacks')
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                config["primary_model"]
            )
        
        # Clear existing fallback configurations
        await db.execute(
            "DELETE FROM system_config WHERE key LIKE 'llm_fallback_%'"
        )
        
        # Insert new fallback configurations
        if "fallbacks" in config:
            for i, fallback in enumerate(config["fallbacks"], 1):
                if "provider" in fallback:
                    await db.execute(
                        """
                        INSERT INTO system_config (key, value, description)
                        VALUES ($1, $2, $3)
                        """,
                        f"llm_fallback_{i}_provider",
                        fallback["provider"],
                        f"Fallback #{i} LLM provider"
                    )
                
                if "model" in fallback:
                    await db.execute(
                        """
                        INSERT INTO system_config (key, value, description)
                        VALUES ($1, $2, $3)
                        """,
                        f"llm_fallback_{i}_model",
                        fallback["model"],
                        f"Fallback #{i} LLM model"
                    )
        
        return {"message": "Global LLM fallback configuration updated successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update global fallback configuration: {str(e)}"
        )