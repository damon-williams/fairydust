from fastapi import Depends, APIRouter, HTTPException, Depends, BackgroundTasks, status, Security
from typing import Optional
import secrets
import string
from uuid import uuid4

from models import (
    OTPRequest, OTPVerify, OAuthCallback, 
    User, UserCreate, UserUpdate, UserPublic,
    Token, AuthResponse
)
from auth import AuthService, get_current_user, TokenData
from shared.database import get_db, Database
from shared.redis_client import get_redis
from shared.email_service import send_otp_email
from shared.sms_service import send_otp_sms

from fastapi.security import HTTPBearer

security = HTTPBearer()

# Constants
INITIAL_DUST_GRANT = 25
FAIRYNAME_LENGTH = 12

# Create routers
auth_router = APIRouter()
user_router = APIRouter()

def generate_fairyname() -> str:
    """Generate a unique fairyname for new users"""
    # Combine adjectives and nouns for whimsical names
    adjectives = ["crystal", "lunar", "stellar", "mystic", "cosmic", "ethereal", "radiant", "twilight"]
    nouns = ["spark", "dream", "wish", "star", "moon", "light", "dawn", "dusk"]
    
    adj = secrets.choice(adjectives)
    noun = secrets.choice(nouns)
    suffix = ''.join(secrets.choice(string.digits) for _ in range(4))
    
    return f"{adj}{noun}{suffix}"

# Authentication Routes
@auth_router.post("/otp/request", response_model=dict)
async def request_otp(
    otp_request: OTPRequest,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r))
):
    """Request OTP for email or phone authentication"""
    # Generate OTP
    otp = await auth_service.generate_otp()
    
    # Store OTP in Redis
    await auth_service.store_otp(otp_request.identifier, otp)
    
    # Send OTP in background
    if otp_request.identifier_type == "email":
        background_tasks.add_task(send_otp_email, otp_request.identifier, otp)
    else:
        background_tasks.add_task(send_otp_sms, otp_request.identifier, otp)
    
    return {
        "message": f"OTP sent to {otp_request.identifier_type}",
        "identifier": otp_request.identifier
    }

@auth_router.post("/otp/verify", response_model=AuthResponse)
async def verify_otp(
    otp_verify: OTPVerify,
    db: Database = Depends(get_db),
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r))
):
    """Verify OTP and create/login user"""
    # Verify OTP
    is_valid = await auth_service.verify_otp(otp_verify.identifier, otp_verify.code)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # Check if user exists
    identifier_type = "email" if "@" in otp_verify.identifier else "phone"
    user = await db.fetch_one(
        f"SELECT * FROM users WHERE {identifier_type} = $1",
        otp_verify.identifier
    )
    
    is_new_user = False
    dust_granted = 0
    
    if not user:
        # Create new user
        is_new_user = True
        dust_granted = INITIAL_DUST_GRANT
        
        user_id = uuid4()
        fairyname = generate_fairyname()
        
        # Check fairyname uniqueness
        while await db.fetch_one("SELECT id FROM users WHERE fairyname = $1", fairyname):
            fairyname = generate_fairyname()
        
        # Create user
        user = await db.fetch_one(
            """
            INSERT INTO users (id, fairyname, email, phone, dust_balance, auth_provider)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            user_id,
            fairyname,
            otp_verify.identifier if identifier_type == "email" else None,
            otp_verify.identifier if identifier_type == "phone" else None,
            dust_granted,
            "otp"
        )
        
        # Log dust grant transaction
        await db.execute(
            """
            INSERT INTO dust_transactions (user_id, amount, type, description)
            VALUES ($1, $2, 'grant', 'Welcome bonus')
            """,
            user_id, dust_granted
        )
    
    # Create tokens
    token_data = {
        "user_id": str(user["id"]),
        "fairyname": user["fairyname"],
        "is_builder": user["is_builder"],
        "is_admin": user.get("is_admin", False)
    }
    
    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)
    
    return AuthResponse(
        user=User(**user),
        token=Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600
        ),
        is_new_user=is_new_user,
        dust_granted=dust_granted
    )

@auth_router.post("/oauth/{provider}", response_model=AuthResponse)
async def oauth_login(
    provider: str,
    callback: OAuthCallback,
    db: Database = Depends(get_db),
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r))
):
    """Handle OAuth callback and create/login user"""
    # Exchange code for token
    token_response = await auth_service.get_oauth_token(provider, callback.code)
    access_token = token_response.get("access_token")
    
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to get access token")
    
    # Get user info from provider
    user_info = await auth_service.get_oauth_user_info(provider, access_token)
    
    if not user_info.get("provider_id"):
        raise HTTPException(status_code=400, detail="Failed to get user info")
    
    # Check if user exists
    user = await db.fetch_one(
        """
        SELECT u.* FROM users u
        JOIN user_auth_providers uap ON u.id = uap.user_id
        WHERE uap.provider = $1 AND uap.provider_user_id = $2
        """,
        provider, user_info["provider_id"]
    )
    
    is_new_user = False
    dust_granted = 0
    
    if not user:
        # Create new user
        is_new_user = True
        dust_granted = INITIAL_DUST_GRANT
        
        user_id = uuid4()
        fairyname = generate_fairyname()
        
        # Check fairyname uniqueness
        while await db.fetch_one("SELECT id FROM users WHERE fairyname = $1", fairyname):
            fairyname = generate_fairyname()
        
        # Create user
        user = await db.fetch_one(
            """
            INSERT INTO users (id, fairyname, email, avatar_url, dust_balance, auth_provider)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            user_id,
            fairyname,
            user_info.get("email"),
            user_info.get("picture"),
            dust_granted,
            provider
        )
        
        # Link OAuth provider
        await db.execute(
            """
            INSERT INTO user_auth_providers (user_id, provider, provider_user_id)
            VALUES ($1, $2, $3)
            """,
            user_id, provider, user_info["provider_id"]
        )
        
        # Log dust grant transaction
        await db.execute(
            """
            INSERT INTO dust_transactions (user_id, amount, type, description)
            VALUES ($1, $2, 'grant', 'Welcome bonus')
            """,
            user_id, dust_granted
        )
    
    # Create tokens
    token_data = {
        "user_id": str(user["id"]),
        "fairyname": user["fairyname"],
        "is_builder": user["is_builder"],
        "is_admin": user.get("is_admin", False)
    }
    
    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)
    
    return AuthResponse(
        user=User(**user),
        token=Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600
        ),
        is_new_user=is_new_user,
        dust_granted=dust_granted
    )

@auth_router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r))
):
    """Refresh access token using refresh token"""
    # Decode refresh token
    token_data = await auth_service.decode_token(refresh_token)
    
    if token_data.type != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")
    
    # Check if refresh token is still valid in Redis
    stored_token = await auth_service.redis.get(f"refresh_token:{token_data.user_id}")
    if not stored_token or stored_token.decode() != refresh_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # Create new access token
    new_token_data = {
        "user_id": token_data.user_id,
        "fairyname": token_data.fairyname,
        "is_builder": token_data.is_builder
    }
    
    new_access_token = await auth_service.create_access_token(new_token_data)
    
    return Token(
        access_token=new_access_token,
        expires_in=3600
    )

@auth_router.post("/logout")
async def logout(
    current_user: TokenData = Depends(get_current_user),
    redis_client = Depends(get_redis),
    credentials = Depends(lambda c=Security(security): c)
):
    """Logout user and revoke tokens"""
    # Revoke access token
    await redis_client.setex(
        f"revoked_token:{credentials.credentials}",
        3600,  # Same as token expiry
        "1"
    )
    
    # Delete refresh token
    await redis_client.delete(f"refresh_token:{current_user.user_id}")
    
    return {"message": "Successfully logged out"}

# User Routes
@user_router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get current user profile"""
    user = await db.fetch_one(
        "SELECT * FROM users WHERE id = $1",
        current_user.user_id
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(**user)

@user_router.patch("/me", response_model=User)
async def update_user_profile(
    update_data: UserUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Update current user profile"""
    # Build update query dynamically
    updates = []
    values = []
    param_count = 1
    
    if update_data.fairyname is not None:
        # Check fairyname uniqueness
        existing = await db.fetch_one(
            "SELECT id FROM users WHERE fairyname = $1 AND id != $2",
            update_data.fairyname, current_user.user_id
        )
        if existing:
            raise HTTPException(status_code=400, detail="Fairyname already taken")
        
        updates.append(f"fairyname = ${param_count}")
        values.append(update_data.fairyname)
        param_count += 1
    
    if update_data.email is not None:
        updates.append(f"email = ${param_count}")
        values.append(update_data.email)
        param_count += 1
    
    if update_data.phone is not None:
        updates.append(f"phone = ${param_count}")
        values.append(update_data.phone)
        param_count += 1
    
    if update_data.avatar_url is not None:
        updates.append(f"avatar_url = ${param_count}")
        values.append(update_data.avatar_url)
        param_count += 1
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Add user_id as last parameter
    values.append(current_user.user_id)
    
    query = f"""
        UPDATE users 
        SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ${param_count}
        RETURNING *
    """
    
    user = await db.fetch_one(query, *values)
    return User(**user)

@user_router.get("/{user_id}/public", response_model=UserPublic)
async def get_user_public_profile(
    user_id: str,
    db: Database = Depends(get_db)
):
    """Get public user profile"""
    user = await db.fetch_one(
        """
        SELECT id, fairyname, avatar_url, is_builder, created_at
        FROM users 
        WHERE id = $1 AND is_active = true
        """,
        user_id
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserPublic(**user)