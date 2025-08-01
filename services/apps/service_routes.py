# services/apps/service_routes.py
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from models import App, AppCategory, AppStatus
from pydantic import BaseModel, Field

from shared.database import Database, get_db

service_router = APIRouter()


class ServiceAppCreate(BaseModel):
    """App creation via service account"""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    icon_url: Optional[str] = None
    category: AppCategory
    website_url: Optional[str] = None
    demo_url: Optional[str] = None
    callback_url: Optional[str] = None
    # Builder information
    builder_email: str = Field(..., description="Email of the app builder/owner")
    builder_name: Optional[str] = Field(None, description="Name of the builder")
    # MCP specific
    framework: Optional[str] = Field(None, description="Framework used (react, vanilla, etc)")
    mcp_version: Optional[str] = Field(None, description="MCP SDK version")


async def verify_service_token(
    x_service_token: str = Header(...), db: Database = Depends(get_db)
) -> dict:
    """Verify service token and return service account info"""
    import logging
    import os

    logger = logging.getLogger(__name__)

    # Check against environment variable
    env_tokens = os.getenv("FAIRYDUST_SERVICE_TOKENS", "")
    logger.info(f"[Service] Raw env tokens: {env_tokens[:20]}... (length: {len(env_tokens)})")
    valid_tokens = [t.strip() for t in env_tokens.split(",") if t.strip()]
    logger.info(
        f"[Service] Checking token: {x_service_token[:8]}... against {len(valid_tokens)} valid tokens"
    )
    logger.info(
        f"[Service] First valid token starts with: {valid_tokens[0][:8] if valid_tokens else 'NO TOKENS'}"
    )

    if x_service_token not in valid_tokens:
        logger.warning(f"[Service] Invalid service token attempted: {x_service_token[:8]}...")
        logger.warning(f"[Service] Token mismatch - received: {x_service_token}")
        logger.warning(f"[Service] Valid tokens from env: {valid_tokens}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token"
        )

    # Return service account info
    # In production, this would come from database
    return {
        "service_id": "mcp-service-account",
        "service_name": "Claude MCP Integration",
        "permissions": ["create_apps", "validate_apps"],
    }


@service_router.post("/apps/register", response_model=App, status_code=status.HTTP_201_CREATED)
async def register_app_via_service(
    app_data: ServiceAppCreate,
    service_account: dict = Depends(verify_service_token),
    db: Database = Depends(get_db),
):
    """Register a new app via service account (for MCP, API integrations)"""
    import logging

    logger = logging.getLogger(__name__)

    logger.info(f"[Service] Registering app: {app_data.name} for builder: {app_data.builder_email}")
    logger.info(f"[Service] Service account: {service_account['service_name']}")

    # First, find or create the builder user
    builder = await db.fetch_one(
        "SELECT id, fairyname FROM users WHERE email = $1", app_data.builder_email
    )

    if not builder:
        # Create a new user for the builder
        # Generate a fairyname for them
        def generate_fairyname() -> str:
            """Generate a unique fairyname for new users"""
            import secrets
            import string

            adjectives = [
                "crystal",
                "lunar",
                "stellar",
                "mystic",
                "cosmic",
                "ethereal",
                "radiant",
                "twilight",
            ]
            nouns = ["spark", "dream", "wish", "star", "moon", "light", "dawn", "dusk"]

            adj = secrets.choice(adjectives)
            noun = secrets.choice(nouns)
            suffix = "".join(secrets.choice(string.digits) for _ in range(4))

            return f"{adj}{noun}{suffix}"

        builder_id = uuid4()
        fairyname = generate_fairyname()

        await db.execute(
            """
            INSERT INTO users (
                id, email, fairyname, dust_balance, is_builder,
                auth_provider, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            builder_id,
            app_data.builder_email,
            fairyname,
            25,  # New users get 25 DUST
            True,  # Mark as builder
            "mcp",  # auth_provider for MCP-created users
            datetime.utcnow(),
            datetime.utcnow(),
        )

        builder_id = builder_id
        builder_fairyname = fairyname
    else:
        builder_id = builder["id"]
        builder_fairyname = builder["fairyname"]

        # Ensure user is marked as builder
        await db.execute("UPDATE users SET is_builder = true WHERE id = $1", builder_id)

    # Create the app
    app_id = uuid4()

    # Build registration metadata
    import json

    registration_metadata = {
        "framework": app_data.framework,
        "mcp_version": app_data.mcp_version,
        "registered_via": "mcp",
        "service_account": service_account["service_name"],
        "timestamp": datetime.utcnow().isoformat(),
    }
    registration_metadata_json = json.dumps(registration_metadata)

    # Insert app into database with registration tracking
    await db.execute(
        """
        INSERT INTO apps (
            id, builder_id, name, slug, description, icon_url,
            status, category, website_url, demo_url, callback_url,
            is_active, registration_source, registered_by_service,
            registration_metadata, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
    """,
        app_id,
        builder_id,
        app_data.name,
        app_data.slug,
        app_data.description,
        app_data.icon_url,
        AppStatus.APPROVED,  # Auto-approve MCP registrations
        app_data.category,
        app_data.website_url,
        app_data.demo_url,
        app_data.callback_url,
        True,  # Active immediately
        "mcp",  # registration_source
        service_account["service_id"],  # registered_by_service
        registration_metadata_json,  # registration_metadata as JSONB
        datetime.utcnow(),
        datetime.utcnow(),
    )

    # Fetch and return the created app
    app_result = await db.fetch_one("SELECT * FROM apps WHERE id = $1", app_id)

    # Add builder info to response
    app_dict = dict(app_result)
    app_dict["builder_fairyname"] = builder_fairyname
    app_dict["builder_email"] = app_data.builder_email

    return App(**app_dict)
