# services/admin/routes/system.py

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_admin_user
from shared.database import Database, get_db

system_router = APIRouter()




@system_router.get("/config")
async def get_system_config(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """Get all system configuration values"""
    configs = await db.fetch_all(
        "SELECT key, value, description, updated_at FROM system_config ORDER BY key"
    )
    return [{"key": c["key"], "value": c["value"], "description": c["description"], "updated_at": c["updated_at"]} for c in configs]


@system_router.get("/config/{key}")
async def get_system_config_value(
    key: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """Get a specific system configuration value"""
    config = await db.fetch_one(
        "SELECT key, value, description, updated_at FROM system_config WHERE key = $1",
        key
    )
    if not config:
        raise HTTPException(status_code=404, detail=f"Configuration key '{key}' not found")
    return {"key": config["key"], "value": config["value"], "description": config["description"], "updated_at": config["updated_at"]}


@system_router.put("/config/{key}")
async def update_system_config_value(
    key: str,
    request: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """Update a specific system configuration value"""
    value = request.get("value")
    description = request.get("description", "")
    
    if value is None:
        raise HTTPException(status_code=400, detail="Value is required")
    
    # Convert value to string for storage
    value_str = str(value)
    
    # Validate certain keys
    if key == "daily_login_bonus_amount":
        try:
            bonus_value = int(value_str)
            if bonus_value < 0:
                raise HTTPException(status_code=400, detail="Daily login bonus must be non-negative")
        except ValueError:
            raise HTTPException(status_code=400, detail="Daily login bonus must be a valid integer")
    elif key == "initial_dust_amount":
        try:
            initial_value = int(value_str)
            if initial_value < 0:
                raise HTTPException(status_code=400, detail="Initial dust amount must be non-negative")
        except ValueError:
            raise HTTPException(status_code=400, detail="Initial dust amount must be a valid integer")
    
    # Check if key exists
    existing = await db.fetch_one(
        "SELECT key FROM system_config WHERE key = $1",
        key
    )
    
    if existing:
        # Update existing
        await db.execute(
            """UPDATE system_config 
               SET value = $1, description = $2, updated_by = $3, updated_at = CURRENT_TIMESTAMP 
               WHERE key = $4""",
            value_str, description, admin_user["user_id"], key
        )
    else:
        # Insert new
        await db.execute(
            """INSERT INTO system_config (key, value, description, updated_by) 
               VALUES ($1, $2, $3, $4)""",
            key, value_str, description, admin_user["user_id"]
        )
    
    return {"key": key, "value": value_str, "description": description, "updated_by": admin_user["fairyname"]}


@system_router.get("/public/config/{key}")
async def get_public_system_config_value(
    key: str,
    db: Database = Depends(get_db)
):
    """Get a public system configuration value (no auth required)"""
    # Only allow certain keys to be accessed publicly
    allowed_public_keys = [
        "daily_login_bonus_amount",
        "initial_dust_amount",
        "app_store_url_ios", 
        "app_store_url_android",
        "support_email",
        "terms_of_service_url",
        "privacy_policy_url",
        "terms_of_service_current_version",
        "privacy_policy_current_version",
        "terms_enforcement_enabled",
        "terms_grace_period_days"
    ]
    
    if key not in allowed_public_keys:
        raise HTTPException(status_code=403, detail=f"Key '{key}' is not publicly accessible")
    
    config = await db.fetch_one(
        "SELECT value FROM system_config WHERE key = $1",
        key
    )
    if not config:
        # Return default values for certain keys
        defaults = {
            "daily_login_bonus_amount": "5",
            "initial_dust_amount": "100",
            "terms_of_service_current_version": "1.0.0",
            "privacy_policy_current_version": "1.0.0",
            "terms_enforcement_enabled": "true",
            "terms_grace_period_days": "7"
        }
        if key in defaults:
            return {"key": key, "value": defaults[key]}
        raise HTTPException(status_code=404, detail=f"Configuration key '{key}' not found")
    
    return {"key": key, "value": config["value"]}