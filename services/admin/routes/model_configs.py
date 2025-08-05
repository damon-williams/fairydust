# services/admin/routes/model_configs.py
"""Proxy endpoints for normalized model configuration management"""

import httpx
from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException

model_configs_router = APIRouter()


@model_configs_router.get("/{app_id}/configs")
async def get_app_model_configs_api(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get all model configurations for an app via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🔧 ADMIN_API: Getting model configs for app {app_id}")

        # Get apps service URL
        import os

        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        # Create admin JWT token for service-to-service auth
        from datetime import datetime, timedelta, timezone

        import jwt

        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
        JWT_ALGORITHM = "HS256"

        # Create token data
        token_data = {
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{apps_url}/model-configs/{app_id}/configs",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Successfully fetched model configs for app {app_id}")
                return result
            else:
                logger.error(f"Apps service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail=f"Apps service error: {response.text}"
                )

    except Exception as e:
        logger.error(f"Error fetching model configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch model configurations")


@model_configs_router.put("/{app_id}/configs/{model_type}")
async def update_app_model_config_by_type_api(
    app_id: str,
    model_type: str,
    model_config: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Update specific model configuration for an app via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🔧 ADMIN_API: Updating {model_type} model config for app {app_id}")
        logger.info(f"🔧 ADMIN_API: Config data: {model_config}")

        # Get apps service URL
        import os

        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        # Create admin JWT token for service-to-service auth
        from datetime import datetime, timedelta, timezone

        import jwt

        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
        JWT_ALGORITHM = "HS256"

        # Create token data
        token_data = {
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{apps_url}/model-configs/{app_id}/configs/{model_type}",
                json=model_config,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ ADMIN_EDIT: Successfully updated {model_type} model config for app {app_id}"
                )
                return result
            else:
                logger.error(f"Apps service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail=f"Apps service error: {response.text}"
                )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating {model_type} model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")


@model_configs_router.post("/{app_id}/configs")
async def create_app_model_config_api(
    app_id: str,
    model_config: dict,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Create model configuration for an app via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🔧 ADMIN_API: Creating model config for app {app_id}")
        logger.info(f"🔧 ADMIN_API: Config data: {model_config}")

        # Get apps service URL
        import os

        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        # Create admin JWT token for service-to-service auth
        from datetime import datetime, timedelta, timezone

        import jwt

        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
        JWT_ALGORITHM = "HS256"

        # Create token data
        token_data = {
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{apps_url}/model-configs/{app_id}/configs",
                json=model_config,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 201:
                result = response.json()
                logger.info(f"✅ ADMIN_EDIT: Successfully created model config for app {app_id}")
                return result
            else:
                logger.error(f"Apps service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail=f"Apps service error: {response.text}"
                )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to create model configuration")


@model_configs_router.delete("/{app_id}/configs/{model_type}")
async def delete_app_model_config_api(
    app_id: str,
    model_type: str,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Delete model configuration for an app via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🔧 ADMIN_API: Deleting {model_type} model config for app {app_id}")

        # Get apps service URL
        import os

        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        # Create admin JWT token for service-to-service auth
        from datetime import datetime, timedelta, timezone

        import jwt

        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
        JWT_ALGORITHM = "HS256"

        # Create token data
        token_data = {
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{apps_url}/model-configs/{app_id}/configs/{model_type}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ ADMIN_EDIT: Successfully deleted {model_type} model config for app {app_id}"
                )
                return result
            else:
                logger.error(f"Apps service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail=f"Apps service error: {response.text}"
                )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete model configuration")


@model_configs_router.get("/fallbacks")
async def get_global_fallbacks_api(
    model_type: str = None,
    admin_user: dict = Depends(get_current_admin_user),
):
    """Get global fallback models via proxy to apps service"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"🔧 ADMIN_API: Getting global fallbacks for model_type: {model_type}")

        # Get apps service URL
        import os

        environment = os.getenv("ENVIRONMENT", "staging")
        base_url_suffix = "production" if environment == "production" else "staging"
        apps_url = f"https://fairydust-apps-{base_url_suffix}.up.railway.app"

        # Create admin JWT token for service-to-service auth
        from datetime import datetime, timedelta, timezone

        import jwt

        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
        JWT_ALGORITHM = "HS256"

        # Create token data
        token_data = {
            "user_id": str(admin_user["user_id"]),
            "fairyname": admin_user["fairyname"],
            "is_admin": True,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Create JWT token
        access_token = jwt.encode(token_data, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        # Build URL with query parameter if model_type is provided
        url = f"{apps_url}/model-configs/fallbacks"
        if model_type:
            url += f"?model_type={model_type}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("✅ Successfully fetched global fallbacks")
                return result
            else:
                logger.error(f"Apps service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code, detail=f"Apps service error: {response.text}"
                )

    except Exception as e:
        logger.error(f"Error fetching global fallbacks: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch global fallbacks")
