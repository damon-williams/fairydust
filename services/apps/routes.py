# services/apps/routes.py
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, Query, status

from models import (
    App, AppCreate, AppValidation, AppStatus
)
from shared.database import get_db, Database
from shared.auth_middleware import get_current_user, require_admin, TokenData

# Create routers
app_router = APIRouter()
admin_router = APIRouter()
marketplace_router = APIRouter()

# ============================================================================
# BASIC APP ROUTES
# ============================================================================

@app_router.post("/", response_model=App, status_code=status.HTTP_201_CREATED)
async def create_app(
    app_data: AppCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Create a new app (builders only)"""
    app_id = uuid4()
    
    # Insert app into database
    await db.execute("""
        INSERT INTO apps (
            id, builder_id, name, slug, description, icon_url,
            status, category, website_url, demo_url, callback_url, is_active
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    """, 
        app_id, UUID(current_user.user_id), app_data.name, app_data.slug,
        app_data.description, app_data.icon_url,
        AppStatus.PENDING, app_data.category, app_data.website_url,
        app_data.demo_url, app_data.callback_url, False
    )
    
    # Fetch the created app
    app_result = await db.fetch_one("SELECT * FROM apps WHERE id = $1", app_id)
    return App(**app_result)

@app_router.get("/validate/{app_id}", response_model=AppValidation)
async def validate_app(
    app_id: UUID,
    db: Database = Depends(get_db)
):
    """Validate app for ledger service"""
    app_data = await db.fetch_one("""
        SELECT id, name, builder_id, status, is_active
        FROM apps WHERE id = $1
    """, app_id)
    
    if not app_data:
        return AppValidation(
            app_id=app_id,
            is_valid=False,
            is_active=False,
            dust_per_use=0,
            name="",
            builder_id=UUID("00000000-0000-0000-0000-000000000000")
        )
    
    is_valid = app_data["status"] == AppStatus.APPROVED
    
    return AppValidation(
        app_id=app_id,
        is_valid=is_valid,
        is_active=app_data["is_active"] and is_valid,
        name=app_data["name"],
        builder_id=app_data["builder_id"]
    )

@admin_router.put("/{app_id}/approve")
async def approve_app(
    app_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Approve an app (admin only)"""
    await db.execute("""
        UPDATE apps 
        SET status = $1, is_active = $2, updated_at = $3
        WHERE id = $4
    """, AppStatus.APPROVED, True, datetime.utcnow(), app_id)
    
    return {"message": "App approved", "app_id": app_id}

@marketplace_router.get("/")
async def browse_marketplace(
    db: Database = Depends(get_db)
):
    """Simple marketplace endpoint"""
    apps = await db.fetch_all("""
        SELECT a.*, u.fairyname as builder_fairyname
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        WHERE a.status = $1 AND a.is_active = $2
        ORDER BY a.created_at DESC
        LIMIT 20
    """, AppStatus.APPROVED, True)
    
    return {"apps": apps}