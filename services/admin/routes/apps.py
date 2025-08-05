import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
import jwt
from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException

# JWT settings for cross-service authentication
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "your-secret-key-here"))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Service URLs
# Determine apps service URL based on environment
environment = os.getenv("ENVIRONMENT", "development")
if environment == "production":
    APPS_SERVICE_URL = "https://fairydust-apps-production.up.railway.app"
elif environment == "staging":
    APPS_SERVICE_URL = "https://fairydust-apps-staging.up.railway.app"
else:
    APPS_SERVICE_URL = os.getenv("APPS_SERVICE_URL", "http://localhost:8003")

apps_router = APIRouter()


@apps_router.get("/api")
async def get_apps_api(
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get apps list as JSON for React app via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "page": page,
                "limit": limit,
            }
            if status and status != "all":
                params["status"] = status

            response = await client.get(
                f"{APPS_SERVICE_URL}/admin/apps/api",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch apps")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching apps: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch apps")


@apps_router.patch("/{app_id}/status")
async def update_app_status_api(
    app_id: str,
    status_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Update app status via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                f"{APPS_SERVICE_URL}/admin/apps/{app_id}/status",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=status_data,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail="Failed to update app status"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating app status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update app status")


@apps_router.delete("/{app_id}")
async def delete_app_api(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Delete app via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{APPS_SERVICE_URL}/admin/apps/{app_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to delete app")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting app: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete app")


@apps_router.post("/api")
async def create_app_api(
    app_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Create app via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{APPS_SERVICE_URL}/admin/apps/api",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=app_data,
            )

            if response.status_code == 201:  # Created status
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to create app")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating app: {e}")
        raise HTTPException(status_code=500, detail="Failed to create app")


@apps_router.put("/{app_id}")
async def update_app_api(
    app_id: str,
    app_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Update app via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{APPS_SERVICE_URL}/admin/apps/{app_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=app_data,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to update app")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating app: {e}")
        raise HTTPException(status_code=500, detail="Failed to update app")


@apps_router.get("/builders")
async def get_builders_api(
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get list of builders for app creation via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{APPS_SERVICE_URL}/admin/apps/builders",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail="Failed to fetch builders"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching builders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch builders")


@apps_router.get("/supported-models")
async def get_supported_models_api(
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get supported LLM models via proxy to apps service"""
    import os

    try:
        # Determine apps service URL based on environment
        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{apps_url}/llm/supported-models")

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code, detail="Failed to fetch supported models"
                )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching supported models: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch supported models")


@apps_router.get("/{app_id}")
async def get_app_api(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get individual app details via proxy to Apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create JWT token for cross-service auth
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Proxy request to apps service
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{APPS_SERVICE_URL}/admin/apps/{app_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Apps service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch app")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching app: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch app")


@apps_router.get("/{app_id}/model-config")
async def get_app_model_config_api(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get app model configuration via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Determine apps service URL based on environment
        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        # Create token data for admin user
        token_data = {
            "sub": str(admin_user["user_id"]),
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "type": "access",
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{apps_url}/llm/{app_id}/model-config",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Successfully fetched model config for app {app_id}")
                return result
            else:
                logger.error(f"❌ Apps service error {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail="Failed to fetch model configuration"
                )

    except Exception as e:
        logger.error(f"Error fetching model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch model configuration")


@apps_router.put("/{app_id}/model-config")
async def update_app_model_config_api(
    app_id: str,
    model_config: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Update app model configuration via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Log the model configuration update attempt
        logger.info(
            f"🔧 ADMIN_EDIT: User {admin_user['fairyname']} updating model config for app {app_id}"
        )
        logger.info(f"🔧 ADMIN_EDIT: New model config: {model_config}")

        # Determine apps service URL based on environment
        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"
        logger.info(f"🔧 ADMIN_EDIT: Sending to apps service: {apps_url}")

        # Create token data for admin user (match auth middleware expectations)
        token_data = {
            "sub": str(admin_user["user_id"]),  # Standard JWT claim
            "user_id": str(admin_user["user_id"]),  # Fallback claim
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "type": "access",
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{apps_url}/llm/{app_id}/model-config",
                json=model_config,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ ADMIN_EDIT: Successfully updated model config for app {app_id}")
                logger.info(f"✅ ADMIN_EDIT: Apps service response: {result}")
                return result
            else:
                logger.error(
                    f"❌ ADMIN_EDIT: Apps service error {response.status_code}: {response.text}"
                )
                raise HTTPException(
                    status_code=response.status_code, detail="Failed to update model configuration"
                )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error updating model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")


# New normalized model configuration proxy endpoints (must be registered with main.py)


@apps_router.post("/{app_id}/model-config/invalidate-cache")
async def invalidate_model_config_cache_api(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Manually invalidate model configuration cache for debugging"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        from shared.app_config_cache import get_app_config_cache

        logger.info(
            f"🗑️ ADMIN_DEBUG: User {admin_user['fairyname']} manually invalidating cache for app {app_id}"
        )

        cache = await get_app_config_cache()
        result = await cache.invalidate_model_config(app_id)

        if result:
            logger.info(f"✅ ADMIN_DEBUG: Successfully invalidated cache for app {app_id}")
            return {"message": f"Cache invalidated for app {app_id}", "success": True}
        else:
            logger.info(f"⚠️ ADMIN_DEBUG: No cache found to invalidate for app {app_id}")
            return {"message": f"No cache found for app {app_id}", "success": False}

    except Exception as e:
        logger.error(f"❌ ADMIN_DEBUG: Error invalidating cache for app {app_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to invalidate cache")


# ============================================================================
# ACTION PRICING ROUTES (PROXY TO APPS SERVICE)
# ============================================================================


@apps_router.get("/pricing/actions")
async def get_action_pricing(
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get action pricing for admin portal"""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Fetching action pricing from: {APPS_SERVICE_URL}/admin/pricing/actions")

    # Create JWT token for cross-service auth
    token_data = {
        "sub": str(admin_user["user_id"]),
        "user_id": str(admin_user["user_id"]),
        "fairyname": admin_user["fairyname"],
        "is_admin": True,
    }
    access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Proxy request to apps service
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{APPS_SERVICE_URL}/admin/pricing/actions",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

        if response.status_code == 200:
            data = response.json()
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Action pricing data from apps service: {data}")
            return data
        else:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to fetch action pricing: {response.status_code} - {response.text}"
            )
            raise HTTPException(
                status_code=response.status_code, detail="Failed to fetch action pricing"
            )


@apps_router.post("/pricing/actions/{action_slug}")
async def create_action_pricing(
    action_slug: str,
    pricing_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Create action pricing via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Creating action pricing for slug: {action_slug}")
    logger.info(f"Pricing data: {pricing_data}")

    # Create JWT token for cross-service auth
    token_data = {
        "sub": str(admin_user["user_id"]),
        "user_id": str(admin_user["user_id"]),
        "fairyname": admin_user["fairyname"],
        "is_admin": True,
    }
    access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Proxy request to apps service
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{APPS_SERVICE_URL}/admin/pricing/actions/{action_slug}",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=pricing_data,
            timeout=30.0,
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Successfully created action pricing for {action_slug}")
            return result
        else:
            logger.error(
                f"❌ Failed to create action pricing: {response.status_code} - {response.text}"
            )
            raise HTTPException(
                status_code=response.status_code, detail="Failed to create action pricing"
            )


@apps_router.put("/pricing/actions/{action_slug}")
async def update_action_pricing(
    action_slug: str,
    pricing_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Update action pricing via proxy to apps service"""

    # Create JWT token for cross-service auth
    token_data = {
        "sub": str(admin_user["user_id"]),
        "user_id": str(admin_user["user_id"]),
        "fairyname": admin_user["fairyname"],
        "is_admin": True,
    }
    access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Proxy request to apps service
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{APPS_SERVICE_URL}/admin/pricing/actions/{action_slug}",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=pricing_data,
            timeout=30.0,
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, detail="Failed to update action pricing"
            )


@apps_router.delete("/pricing/actions/{action_slug}")
async def delete_action_pricing(
    action_slug: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Delete action pricing via proxy to apps service"""

    # Create JWT token for cross-service auth
    token_data = {
        "sub": str(admin_user["user_id"]),
        "user_id": str(admin_user["user_id"]),
        "fairyname": admin_user["fairyname"],
        "is_admin": True,
    }
    access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Proxy request to apps service
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{APPS_SERVICE_URL}/admin/pricing/actions/{action_slug}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, detail="Failed to delete action pricing"
            )
