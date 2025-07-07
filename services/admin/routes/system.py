# services/admin/routes/system.py

import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends
from shared.auth_middleware import get_current_admin_user

# JWT Configuration - same as identity service
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"

system_router = APIRouter()


@system_router.post("/service-token/generate")
async def generate_service_token(admin_user: dict = Depends(get_current_admin_user)):
    """Generate a long-lived service JWT token for service-to-service authentication"""
    
    # Use the current admin user's ID for the service token
    admin_user_id = admin_user["user_id"]
    
    # Token payload - long-lived service token with admin privileges
    payload = {
        "user_id": admin_user_id,
        "sub": admin_user_id,  # Standard JWT subject claim
        "fairyname": f"SERVICE_TOKEN_{admin_user['fairyname']}",
        "email": admin_user.get("email", "service@fairydust.internal"),
        "is_admin": True,
        "is_builder": True,
        "type": "service",
        "iat": datetime.utcnow().timestamp(),  # Issued at
        "generated_by": admin_user_id,
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # Set expiration to 10 years (very long-lived but not infinite)
    expires_years = 10
    expire_date = datetime.utcnow() + timedelta(days=365 * expires_years)
    payload["exp"] = expire_date.timestamp()
    
    # Generate the token
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    return {
        "token": token,
        "expires": expire_date.isoformat(),
        "generated_for": admin_user["fairyname"],
        "usage": "Set this as SERVICE_JWT_TOKEN environment variable in apps service"
    }