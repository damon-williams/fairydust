from fastapi import Depends, APIRouter, HTTPException, Depends, BackgroundTasks, status, Security
from typing import Optional, List
import secrets
import string
from uuid import uuid4
import json
import httpx
import os

from models import (
    OTPRequest, OTPVerify, OAuthCallback, 
    User, UserCreate, UserUpdate, UserPublic,
    Token, AuthResponse,
    UserProfileData, UserProfileDataCreate, UserProfileDataUpdate,
    PersonInMyLife, PersonInMyLifeCreate, PersonInMyLifeUpdate,
    PersonProfileData, PersonProfileDataCreate,
    QuestionResponseSubmission, UserQuestionResponse,
    LocalProfileData, AIContextResponse, ProfileDataBatch
)
from auth import AuthService, get_current_user, TokenData
from shared.database import get_db, Database
from shared.redis_client import get_redis
from shared.email_service import send_otp_email
from shared.sms_service import send_otp_sms
from shared.streak_utils import calculate_daily_streak
from shared.json_utils import parse_profile_data, parse_people_profile_data

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
        f"""SELECT id, fairyname, email, phone, avatar_url, is_builder, is_admin, is_active,
                  first_name, age_range, city, country, dust_balance, auth_provider,
                  last_profiling_session, total_profiling_sessions, streak_days, last_login_date,
                  created_at, updated_at 
           FROM users WHERE {identifier_type} = $1""",
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
        
        # Check fairyname uniqueness with limited retries to prevent infinite loops
        max_retries = 10
        for _ in range(max_retries):
            if not await db.fetch_one("SELECT id FROM users WHERE fairyname = $1", fairyname):
                break
            fairyname = generate_fairyname()
        else:
            # If we couldn't find unique name after 10 tries, add timestamp
            import time
            fairyname = f"{fairyname}{int(time.time() % 10000)}"
        
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
    
    # Calculate and update daily login streak
    streak_days, last_login_date = await calculate_daily_streak(
        db, 
        str(user["id"]), 
        user.get("streak_days", 0), 
        user.get("last_login_date")
    )
    
    # Update user dict with new streak info (avoid redundant DB query)
    user_dict = dict(user)
    user_dict["streak_days"] = streak_days
    user_dict["last_login_date"] = last_login_date
    user = user_dict
    
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
        
        # Check fairyname uniqueness with limited retries to prevent infinite loops
        max_retries = 10
        for _ in range(max_retries):
            if not await db.fetch_one("SELECT id FROM users WHERE fairyname = $1", fairyname):
                break
            fairyname = generate_fairyname()
        else:
            # If we couldn't find unique name after 10 tries, add timestamp
            import time
            fairyname = f"{fairyname}{int(time.time() % 10000)}"
        
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
    
    # Calculate and update daily login streak
    streak_days, last_login_date = await calculate_daily_streak(
        db, 
        str(user["id"]), 
        user.get("streak_days", 0), 
        user.get("last_login_date")
    )
    
    # Update user dict with new streak info (avoid redundant DB query)
    user_dict = dict(user)
    user_dict["streak_days"] = streak_days
    user_dict["last_login_date"] = last_login_date
    user = user_dict
    
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
        """SELECT id, fairyname, email, phone, avatar_url, is_builder, is_admin, is_active,
                  first_name, age_range, city, country, dust_balance, auth_provider,
                  last_profiling_session, total_profiling_sessions, streak_days, last_login_date,
                  created_at, updated_at 
           FROM users WHERE id = $1""",
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
    
    if update_data.first_name is not None:
        updates.append(f"first_name = ${param_count}")
        values.append(update_data.first_name)
        param_count += 1
    
    if update_data.age_range is not None:
        updates.append(f"age_range = ${param_count}")
        values.append(update_data.age_range)
        param_count += 1
    
    if update_data.city is not None:
        updates.append(f"city = ${param_count}")
        values.append(update_data.city)
        param_count += 1
    
    if update_data.country is not None:
        updates.append(f"country = ${param_count}")
        values.append(update_data.country)
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

# Progressive Profiling Routes

@user_router.get("/{user_id}/profile-data", response_model=List[UserProfileData])
async def get_user_profile_data(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    category: Optional[str] = None
):
    """Get user's profile data"""
    # Users can only access their own profile data
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = "SELECT * FROM user_profile_data WHERE user_id = $1"
    params = [user_id]
    
    if category:
        query += " AND category = $2"
        params.append(category)
    
    query += " ORDER BY updated_at DESC"
    
    profile_data = await db.fetch_all(query, *params)
    return [UserProfileData(**data) for data in profile_data]

@user_router.patch("/{user_id}/profile-data", response_model=List[UserProfileData])
async def update_user_profile_data(
    user_id: str,
    profile_batch: ProfileDataBatch,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Update user profile data (batch operation)"""
    # Users can only update their own profile data
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    updated_data = []
    
    for profile_data in profile_batch.profile_data:
        # Serialize field_value for JSONB storage
        field_value_json = json.dumps(profile_data.field_value)
        
        # Check if field exists
        existing = await db.fetch_one(
            "SELECT id FROM user_profile_data WHERE user_id = $1 AND field_name = $2",
            user_id, profile_data.field_name
        )
        
        if existing:
            # Update existing
            updated = await db.fetch_one(
                """
                UPDATE user_profile_data 
                SET field_value = $1::jsonb, confidence_score = $2, source = $3, 
                    app_context = $4, category = $5, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $6 AND field_name = $7
                RETURNING *
                """,
                field_value_json, profile_data.confidence_score, 
                profile_data.source, profile_data.app_context, profile_data.category,
                user_id, profile_data.field_name
            )
        else:
            # Create new
            updated = await db.fetch_one(
                """
                INSERT INTO user_profile_data 
                (user_id, category, field_name, field_value, confidence_score, source, app_context)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                RETURNING *
                """,
                user_id, profile_data.category, profile_data.field_name, 
                field_value_json, profile_data.confidence_score, 
                profile_data.source, profile_data.app_context
            )
        
        updated_data.append(UserProfileData(**updated))
    
    return updated_data

@user_router.post("/{user_id}/people", response_model=PersonInMyLife)
async def add_person_to_life(
    user_id: str,
    person: PersonInMyLifeCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Add person to user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_person = await db.fetch_one(
        """
        INSERT INTO people_in_my_life (user_id, name, age_range, relationship)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        user_id, person.name, person.age_range, person.relationship
    )
    
    return PersonInMyLife(**new_person)

@user_router.get("/{user_id}/people", response_model=List[PersonInMyLife])
async def get_people_in_my_life(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get all people in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    people = await db.fetch_all(
        "SELECT * FROM people_in_my_life WHERE user_id = $1 ORDER BY created_at ASC",
        user_id
    )
    
    return [PersonInMyLife(**person) for person in people]

@user_router.patch("/{user_id}/people/{person_id}", response_model=PersonInMyLife)
async def update_person_in_my_life(
    user_id: str,
    person_id: str,
    person_update: PersonInMyLifeUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Update person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify person belongs to user
    existing = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id, user_id
    )
    
    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Build update query
    updates = []
    values = []
    param_count = 1
    
    if person_update.name is not None:
        updates.append(f"name = ${param_count}")
        values.append(person_update.name)
        param_count += 1
    
    if person_update.age_range is not None:
        updates.append(f"age_range = ${param_count}")
        values.append(person_update.age_range)
        param_count += 1
    
    if person_update.relationship is not None:
        updates.append(f"relationship = ${param_count}")
        values.append(person_update.relationship)
        param_count += 1
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    values.append(person_id)
    
    query = f"""
        UPDATE people_in_my_life 
        SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ${param_count}
        RETURNING *
    """
    
    updated_person = await db.fetch_one(query, *values)
    return PersonInMyLife(**updated_person)

@user_router.delete("/{user_id}/people/{person_id}")
async def remove_person_from_life(
    user_id: str,
    person_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Remove person from user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify person belongs to user before deletion
    existing = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id, user_id
    )
    
    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")
    
    await db.execute(
        "DELETE FROM people_in_my_life WHERE id = $1",
        person_id
    )
    
    return {"message": "Person removed successfully"}

@user_router.post("/{user_id}/people/{person_id}/profile-data", response_model=PersonProfileData)
async def add_person_profile_data(
    user_id: str,
    person_id: str,
    profile_data: PersonProfileDataCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Add profile data for person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify person belongs to user
    person = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id, user_id
    )
    
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Serialize field_value for JSONB storage
    field_value_json = json.dumps(profile_data.field_value)
    
    # Upsert person profile data
    existing = await db.fetch_one(
        "SELECT id FROM person_profile_data WHERE person_id = $1 AND field_name = $2",
        person_id, profile_data.field_name
    )
    
    if existing:
        updated = await db.fetch_one(
            """
            UPDATE person_profile_data 
            SET field_value = $1::jsonb, confidence_score = $2, source = $3, 
                category = $4, updated_at = CURRENT_TIMESTAMP
            WHERE person_id = $5 AND field_name = $6
            RETURNING *
            """,
            field_value_json, profile_data.confidence_score,
            profile_data.source, profile_data.category, person_id, profile_data.field_name
        )
    else:
        updated = await db.fetch_one(
            """
            INSERT INTO person_profile_data 
            (person_id, user_id, category, field_name, field_value, confidence_score, source)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            RETURNING *
            """,
            person_id, user_id, profile_data.category, profile_data.field_name,
            field_value_json, profile_data.confidence_score, profile_data.source
        )
    
    return PersonProfileData(**updated)

@user_router.get("/{user_id}/people/{person_id}/profile-data", response_model=List[PersonProfileData])
async def get_person_profile_data(
    user_id: str,
    person_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get profile data for person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify person belongs to user
    person = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id, user_id
    )
    
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    profile_data = await db.fetch_all(
        "SELECT * FROM person_profile_data WHERE person_id = $1 ORDER BY updated_at DESC",
        person_id
    )
    
    return [PersonProfileData(**data) for data in profile_data]

@user_router.get("/{user_id}/ai-context", response_model=AIContextResponse)
async def get_ai_context(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    redis_client = Depends(get_redis),
    app_id: Optional[str] = None
):
    """Get AI context for LLM personalization"""
    import json
    
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check cache first
    cache_key = f"ai_context:{user_id}"
    if app_id:
        cache_key += f":{app_id}"
    
    cached_context = await redis_client.get(cache_key)
    if cached_context:
        return AIContextResponse(**json.loads(cached_context))
    
    # Get user profile data
    user_profile = await db.fetch_all(
        "SELECT * FROM user_profile_data WHERE user_id = $1",
        user_id
    )
    
    # Get people in user's life with their profile data
    people = await db.fetch_all(
        """
        SELECT p.*, 
               COALESCE(
                   json_agg(
                       json_build_object(
                           'field_name', ppd.field_name,
                           'field_value', ppd.field_value,
                           'category', ppd.category
                       )
                   ) FILTER (WHERE ppd.id IS NOT NULL), 
                   '[]'
               ) as profile_data
        FROM people_in_my_life p
        LEFT JOIN person_profile_data ppd ON p.id = ppd.person_id
        WHERE p.user_id = $1
        GROUP BY p.id, p.name, p.age_range, p.relationship, p.created_at, p.updated_at
        ORDER BY p.created_at ASC
        """,
        user_id
    )
    
    # Build user context string
    user_traits = {}
    for profile in user_profile:
        category = profile['category']
        field_name = profile['field_name']
        field_value = profile['field_value']
        
        # Parse profile field value using centralized utility
        field_value = parse_profile_data(field_value, field_name)
        
        if category not in user_traits:
            user_traits[category] = {}
        user_traits[category][field_name] = field_value
    
    user_context_parts = []
    
    # Add personality traits
    if 'personality' in user_traits:
        personality = user_traits['personality']
        if 'adventure_level' in personality:
            level = personality['adventure_level']
            try:
                level = int(level) if isinstance(level, str) else level
                if level >= 4:
                    user_context_parts.append("Adventure level: high")
                elif level >= 3:
                    user_context_parts.append("Adventure level: moderate") 
                else:
                    user_context_parts.append("Adventure level: low")
            except (ValueError, TypeError):
                # Skip if level can't be converted to int
                pass
        
        if 'creativity_level' in personality:
            level = personality['creativity_level']
            try:
                level = int(level) if isinstance(level, str) else level
                if level >= 4:
                    user_context_parts.append("Creativity level: very creative")
                elif level >= 3:
                    user_context_parts.append("Creativity level: creative")
                else:
                    user_context_parts.append("Creativity level: practical")
            except (ValueError, TypeError):
                # Skip if level can't be converted to int
                pass
    
    # Add interests
    if 'interests' in user_traits and 'interests' in user_traits['interests']:
        interests = user_traits['interests']['interests']
        if isinstance(interests, list):
            user_context_parts.append(f"Interests: {', '.join(interests)}")
    
    # Add goals
    if 'goals' in user_traits and 'lifestyle_goals' in user_traits['goals']:
        goals = user_traits['goals']['lifestyle_goals']
        if isinstance(goals, list):
            user_context_parts.append(f"Goals: {', '.join(goals)}")
    
    # Add dietary preferences
    if 'cooking' in user_traits and 'dietary_preferences' in user_traits['cooking']:
        dietary = user_traits['cooking']['dietary_preferences']
        if isinstance(dietary, list):
            user_context_parts.append(f"Dietary: {', '.join(dietary)}")
    
    user_context = ". ".join(user_context_parts) if user_context_parts else "No profile data available"
    
    # Build relationship context
    relationship_context = []
    for person in people:
        name = person['name']
        age_range = person['age_range'] or 'unknown age'
        relationship = person['relationship'] or 'person'
        
        person_context_parts = []
        profile_data = person['profile_data']
        
        # Parse people profile data using centralized utility
        profile_data = parse_people_profile_data(profile_data)
        
        # Parse person's profile data
        person_traits = {}
        for data in profile_data:
            if isinstance(data, dict) and data.get('field_name') and data.get('field_value'):
                person_traits[data['field_name']] = data['field_value']
        
        # Build person context
        if 'interests' in person_traits:
            interests = person_traits['interests']
            if isinstance(interests, list):
                person_context_parts.append(f"Interests: {', '.join(interests)}")
        
        if 'food_preferences' in person_traits:
            food_prefs = person_traits['food_preferences']
            if isinstance(food_prefs, dict):
                if 'likes' in food_prefs:
                    person_context_parts.append(f"Likes: {', '.join(food_prefs['likes'])}")
                if 'dislikes' in food_prefs:
                    person_context_parts.append(f"Dislikes: {', '.join(food_prefs['dislikes'])}")
        
        person_context = ". ".join(person_context_parts) if person_context_parts else "Limited profile data"
        
        relationship_context.append({
            "person": f"{name} ({relationship}, {age_range})",
            "relationship": relationship,
            "context": person_context,
            "suggestions_for": ["quality_time", "gift_ideas", "activities"]
        })
    
    # Build app-specific context
    app_specific_context = {}
    
    if app_id == "fairydust-inspire" or not app_id:
        inspire_context = "Focus on personalized activity suggestions"
        if relationship_context:
            inspire_context += " that work well for relationships"
        if 'personality' in user_traits:
            adventure = user_traits['personality'].get('adventure_level', 3)
            if adventure >= 4:
                inspire_context += ". Suggest adventurous activities"
            elif adventure <= 2:
                inspire_context += ". Suggest calm, low-key activities"
        app_specific_context["fairydust-inspire"] = inspire_context
    
    if app_id == "fairydust-recipe" or not app_id:
        recipe_context = "Provide personalized recipe suggestions"
        if 'cooking' in user_traits:
            dietary = user_traits['cooking'].get('dietary_preferences', [])
            if dietary:
                # Ensure dietary is a list before joining
                if isinstance(dietary, list):
                    recipe_context += f". Must accommodate: {', '.join(dietary)}"
                elif isinstance(dietary, str):
                    # If it's still a string, try to parse it as JSON one more time
                    try:
                        dietary_list = json.loads(dietary)
                        if isinstance(dietary_list, list):
                            recipe_context += f". Must accommodate: {', '.join(dietary_list)}"
                        else:
                            recipe_context += f". Must accommodate: {dietary}"
                    except (json.JSONDecodeError, ValueError):
                        recipe_context += f". Must accommodate: {dietary}"
                else:
                    recipe_context += f". Must accommodate: {dietary}"
            skill = user_traits['cooking'].get('cooking_skill_level')
            if skill:
                recipe_context += f". Cooking skill: {skill}"
        app_specific_context["fairydust-recipe"] = recipe_context
    
    # Build response
    ai_context = AIContextResponse(
        user_context=user_context,
        relationship_context=relationship_context,
        app_specific_context=app_specific_context
    )
    
    # Cache for 15 minutes
    await redis_client.setex(
        cache_key,
        900,  # 15 minutes
        json.dumps(ai_context.dict())
    )
    
    return ai_context

@user_router.post("/{user_id}/question-responses")
async def submit_question_responses(
    user_id: str,
    responses: QuestionResponseSubmission,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Submit question responses and award DUST"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    total_dust_awarded = 0
    saved_responses = []
    
    for response in responses.responses:
        # Debug logging  
        print(f"DEBUG: Received response_value type: {type(response.response_value)}")
        print(f"DEBUG: Received response_value content: {response.response_value}")
        
        # Check if question already answered
        existing = await db.fetch_one(
            "SELECT id FROM user_question_responses WHERE user_id = $1 AND question_id = $2",
            user_id, response.question_id
        )
        
        if existing:
            continue  # Skip already answered questions
        
        # No DUST reward for profile questions
        dust_reward = 0
        
        # Ensure response_value is properly formatted for JSONB
        # asyncpg requires JSON string for JSONB fields, not Python objects
        if isinstance(response.response_value, (dict, list)):
            response_value = json.dumps(response.response_value)
        else:
            response_value = json.dumps(response.response_value)
        
        print(f"DEBUG: Storing response_value type: {type(response_value)}")
        print(f"DEBUG: Storing response_value content: {response_value}")
        
        # Save response
        saved_response = await db.fetch_one(
            """
            INSERT INTO user_question_responses 
            (user_id, question_id, response_value, session_id, dust_reward)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            RETURNING *
            """,
            user_id, response.question_id, response_value, 
            responses.session_id, dust_reward
        )
        
        saved_responses.append(UserQuestionResponse(**saved_response))
    
    # Update user's profiling session count if any questions were answered
    if len(saved_responses) > 0:
        await db.execute(
            """
            UPDATE users 
            SET total_profiling_sessions = total_profiling_sessions + 1,
                last_profiling_session = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            user_id
        )
    
    # Invalidate AI context cache
    redis_client = await get_redis()
    cache_pattern = f"ai_context:{user_id}*"
    # In production, you'd want a more sophisticated cache invalidation
    await redis_client.delete(f"ai_context:{user_id}")
    
    return {
        "responses_saved": len(saved_responses),
        "dust_awarded": 0,
        "responses": saved_responses
    }

@user_router.post("/{user_id}/migrate-local-data")
async def migrate_local_data(
    user_id: str,
    local_data: LocalProfileData,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Migrate local profile data to backend"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    migrated_items = {
        "profile_fields": 0,
        "people": 0,
        "answered_questions": 0
    }
    
    profile = local_data.profile
    
    # Helper function to convert age to age_range
    def age_to_range(age):
        if age <= 2:
            return 'infant'
        elif age <= 5:
            return 'toddler'
        elif age <= 12:
            return 'child'
        elif age <= 17:
            return 'teen'
        elif age <= 25:
            return 'young_adult'
        elif age <= 40:
            return 'adult'
        elif age <= 60:
            return 'middle_aged'
        else:
            return 'senior'
    
    # Update basic profile fields that go in users table
    basic_fields = ['first_name', 'age_range', 'city', 'country']
    user_updates = {}
    for field in basic_fields:
        if field in profile:
            user_updates[field] = profile[field]
    
    if user_updates:
        update_parts = []
        values = []
        param_count = 1
        
        for field, value in user_updates.items():
            update_parts.append(f"{field} = ${param_count}")
            values.append(value)
            param_count += 1
        
        values.append(user_id)
        
        await db.execute(
            f"""
            UPDATE users 
            SET {', '.join(update_parts)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ${param_count}
            """,
            *values
        )
    
    # Migrate progressive profiling fields
    profile_field_mapping = {
        'interests': ('interests', 'interests'),
        'dietary_preferences': ('cooking', 'dietary_preferences'),
        'cooking_skill_level': ('cooking', 'cooking_skill_level'),
        'lifestyle_goals': ('goals', 'lifestyle_goals'),
        'personality_traits': ('personality', 'personality_traits'),
        'adventure_level': ('personality', 'adventure_level'),
        'creativity_level': ('personality', 'creativity_level'),
        'social_preference': ('personality', 'social_preference')
    }
    
    for field_name, (category, profile_field) in profile_field_mapping.items():
        if field_name in profile:
            # Serialize field_value for JSONB and upsert profile data
            field_value_json = json.dumps(profile[field_name])
            await db.execute(
                """
                INSERT INTO user_profile_data 
                (user_id, category, field_name, field_value, source)
                VALUES ($1, $2, $3, $4::jsonb, 'migration')
                ON CONFLICT (user_id, field_name) 
                DO UPDATE SET 
                    field_value = EXCLUDED.field_value,
                    source = 'migration',
                    updated_at = CURRENT_TIMESTAMP
                """,
                user_id, category, profile_field, field_value_json
            )
            migrated_items["profile_fields"] += 1
    
    # Migrate people in my life
    for person_data in local_data.people_in_my_life:
        name = person_data.get('name')
        age = person_data.get('age')
        relationship = person_data.get('relationship')
        
        if not name:
            continue
        
        # Convert age to age_range
        age_range = age_to_range(age) if age else None
        
        # Check if person already exists
        existing_person = await db.fetch_one(
            "SELECT id FROM people_in_my_life WHERE user_id = $1 AND name = $2",
            user_id, name
        )
        
        if not existing_person:
            await db.execute(
                """
                INSERT INTO people_in_my_life (user_id, name, age_range, relationship)
                VALUES ($1, $2, $3, $4)
                """,
                user_id, name, age_range, relationship
            )
            migrated_items["people"] += 1
    
    # Migrate answered questions
    progressive_state = profile.get('progressive_profiling_state', {})
    answered_questions = progressive_state.get('questions_answered', [])
    
    for question_id in answered_questions:
        # Check if already recorded
        existing = await db.fetch_one(
            "SELECT id FROM user_question_responses WHERE user_id = $1 AND question_id = $2",
            user_id, question_id
        )
        
        if not existing:
            # Create placeholder response (we don't have the actual response value)
            await db.execute(
                """
                INSERT INTO user_question_responses 
                (user_id, question_id, response_value, session_id, dust_reward)
                VALUES ($1, $2, $3, 'migration', 0)
                """,
                user_id, question_id, {"migrated": True}
            )
            migrated_items["answered_questions"] += 1
    
    # Update profiling session stats
    total_sessions = progressive_state.get('total_sessions', 0)
    if total_sessions > 0:
        await db.execute(
            "UPDATE users SET total_profiling_sessions = $1 WHERE id = $2",
            total_sessions, user_id
        )
    
    return {
        "success": True,
        "migrated": migrated_items,
        "message": f"Successfully migrated {sum(migrated_items.values())} items"
    }

@user_router.get("/questions", response_model=dict)
async def get_all_questions(
    db: Database = Depends(get_db)
):
    """Get all available profiling questions from the database"""
    questions_data = await db.fetch_all(
        """
        SELECT id, category, question_text, question_type, profile_field, 
               priority, app_context, min_app_uses, options, is_active
        FROM profiling_questions 
        WHERE is_active = true
        ORDER BY priority DESC, category, id
        """
    )
    
    questions = []
    for q in questions_data:
        question = {
            "id": q["id"],
            "category": q["category"],
            "question": q["question_text"],
            "type": q["question_type"],
            "profile_field": q["profile_field"],
            "priority": q["priority"],
            "app_context": q["app_context"] or [],
            "min_app_uses": q["min_app_uses"],
            "options": q["options"] or []
        }
        questions.append(question)
    
    return {"questions": questions}

@user_router.get("/{user_id}/question-responses", response_model=dict)
async def get_user_question_responses(
    user_id: str,
    db: Database = Depends(get_db)
):
    """Get all question responses for a specific user"""
    responses_data = await db.fetch_all(
        """
        SELECT question_id, response_value, session_id, answered_at as created_at
        FROM user_question_responses 
        WHERE user_id = $1
        ORDER BY answered_at DESC
        """,
        user_id
    )
    
    responses = []
    for r in responses_data:
        response = {
            "question_id": r["question_id"],
            "response_value": r["response_value"],
            "session_id": r["session_id"],
            "created_at": r["created_at"]
        }
        responses.append(response)
    
    return {"responses": responses}