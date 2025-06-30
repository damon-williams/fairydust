import uuid
from typing import Optional

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException

from shared.database import Database, get_db

apps_router = APIRouter()


@apps_router.get("/api")
async def get_apps_api(
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get apps list as JSON for React app"""
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


@apps_router.patch("/{app_id}/status")
async def update_app_status_api(
    app_id: str,
    status_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update app status via API for React app"""
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
        f"Status changed to {status} by {admin_user['fairyname']}",
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


@apps_router.delete("/{app_id}")
async def delete_app_api(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Delete app via API for React app"""
    # Check if app exists
    app = await db.fetch_one("SELECT id, name FROM apps WHERE id = $1", app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Delete the app
    await db.execute("DELETE FROM apps WHERE id = $1", app_id)

    return {"message": f"App '{app['name']}' deleted successfully"}


@apps_router.post("/api")
async def create_app_api(
    app_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Create app via API for React app"""
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
        app_id = uuid.uuid4()

        await db.execute(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            app_id,
            uuid.UUID(builder_id),
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
            f"Created by admin {admin_user['fairyname']}",
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


@apps_router.put("/{app_id}")
async def update_app_api(
    app_id: str,
    app_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update app via API for React app"""
    try:
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
            slug_check = await db.fetch_one("SELECT id FROM apps WHERE slug = $1 AND id != $2", slug, app_id)
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

        return dict(app)

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error updating app via API: {e}")
        raise HTTPException(status_code=500, detail="Failed to update app")


@apps_router.get("/builders")
async def get_builders_api(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get list of builders for app creation"""
    builders = await db.fetch_all(
        "SELECT id, fairyname, email FROM users WHERE is_builder = true ORDER BY fairyname"
    )
    return [dict(builder) for builder in builders]


@apps_router.get("/supported-models")
async def get_supported_models_api(
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get supported LLM models via proxy to apps service"""
    import httpx
    import os
    
    try:
        # Determine apps service URL based on environment
        environment = os.getenv('ENVIRONMENT', 'staging')
        base_url_suffix = 'production' if environment == 'production' else 'staging'
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{apps_url}/llm/supported-models")
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch supported models")
                
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching supported models: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch supported models")


@apps_router.put("/{app_id}/model-config")
async def update_app_model_config_api(
    app_id: str,
    model_config: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Update app model configuration via proxy to apps service"""
    import httpx
    import os
    import jwt
    from datetime import datetime, timedelta
    
    try:
        # Determine apps service URL based on environment
        environment = os.getenv('ENVIRONMENT', 'staging')
        base_url_suffix = 'production' if environment == 'production' else 'staging'
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"
        
        # Create JWT token for apps service authentication
        # Use same JWT settings as identity service
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
        ALGORITHM = "HS256"
        ACCESS_TOKEN_EXPIRE_MINUTES = 60
        
        # Create token data for admin user
        token_data = {
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "type": "access"
        }
        
        # Create JWT token
        access_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{apps_url}/llm/{app_id}/model-config",
                json=model_config,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to update model configuration")
                
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")
