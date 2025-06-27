import json
import secrets
import string
from typing import Optional
from uuid import uuid4

from auth import AuthService, TokenData, get_current_user
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from models import (
    AuthResponse,
    LocalProfileData,
    OAuthCallback,
    OTPRequest,
    OTPVerify,
    PersonInMyLife,
    PersonInMyLifeCreate,
    PersonInMyLifeUpdate,
    PersonProfileData,
    PersonProfileDataCreate,
    ProfileDataBatch,
    RefreshTokenRequest,
    Token,
    User,
    UserProfileData,
    UserPublic,
    UserUpdate,
)

from shared.database import Database, get_db
from shared.email_service import send_otp_email
from shared.json_utils import parse_people_profile_data, parse_profile_data
from shared.redis_client import get_redis
from shared.sms_service import send_otp_sms
from shared.streak_utils import calculate_daily_streak

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


# Authentication Routes
@auth_router.post("/otp/request", response_model=dict)
async def request_otp(
    otp_request: OTPRequest,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r)),
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
        "identifier": otp_request.identifier,
    }


@auth_router.post("/otp/verify", response_model=AuthResponse)
async def verify_otp(
    otp_verify: OTPVerify,
    db: Database = Depends(get_db),
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r)),
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
        otp_verify.identifier,
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
            "otp",
        )

        # Log dust grant transaction
        await db.execute(
            """
            INSERT INTO dust_transactions (user_id, amount, type, description)
            VALUES ($1, $2, 'grant', 'Welcome bonus')
            """,
            user_id,
            dust_granted,
        )

    # Calculate and update daily login streak
    streak_days, last_login_date = await calculate_daily_streak(
        db, str(user["id"]), user.get("streak_days", 0), user.get("last_login_date")
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
        "is_admin": user.get("is_admin", False),
    }

    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)

    return AuthResponse(
        user=User(**user),
        token=Token(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        is_new_user=is_new_user,
        dust_granted=dust_granted,
    )


@auth_router.post("/oauth/{provider}", response_model=AuthResponse)
async def oauth_login(
    provider: str,
    callback: OAuthCallback,
    db: Database = Depends(get_db),
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r)),
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
        provider,
        user_info["provider_id"],
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
            provider,
        )

        # Link OAuth provider
        await db.execute(
            """
            INSERT INTO user_auth_providers (user_id, provider, provider_user_id)
            VALUES ($1, $2, $3)
            """,
            user_id,
            provider,
            user_info["provider_id"],
        )

        # Log dust grant transaction
        await db.execute(
            """
            INSERT INTO dust_transactions (user_id, amount, type, description)
            VALUES ($1, $2, 'grant', 'Welcome bonus')
            """,
            user_id,
            dust_granted,
        )

    # Calculate and update daily login streak
    streak_days, last_login_date = await calculate_daily_streak(
        db, str(user["id"]), user.get("streak_days", 0), user.get("last_login_date")
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
        "is_admin": user.get("is_admin", False),
    }

    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)

    return AuthResponse(
        user=User(**user),
        token=Token(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        is_new_user=is_new_user,
        dust_granted=dust_granted,
    )


@auth_router.post("/refresh", response_model=Token)
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r)),
):
    """Refresh access token using refresh token"""
    # Decode refresh token
    token_data = await auth_service.decode_token(request.refresh_token)

    if token_data.type != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")

    # Check if refresh token is still valid in Redis
    stored_token = await auth_service.redis.get(f"refresh_token:{token_data.user_id}")
    if not stored_token or stored_token.decode() != request.refresh_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Create new access token
    new_token_data = {
        "user_id": token_data.user_id,
        "fairyname": token_data.fairyname,
        "is_builder": token_data.is_builder,
    }

    new_access_token = await auth_service.create_access_token(new_token_data)

    return Token(access_token=new_access_token, expires_in=3600)


@auth_router.post("/logout")
async def logout(
    current_user: TokenData = Depends(get_current_user),
    redis_client=Depends(get_redis),
    credentials=Depends(lambda c=Security(security): c),
):
    """Logout user and revoke tokens"""
    # Revoke access token
    await redis_client.setex(
        f"revoked_token:{credentials.credentials}", 3600, "1"  # Same as token expiry
    )

    # Delete refresh token
    await redis_client.delete(f"refresh_token:{current_user.user_id}")

    return {"message": "Successfully logged out"}


# User Routes
@user_router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: TokenData = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Get current user profile"""
    user = await db.fetch_one(
        """SELECT id, fairyname, email, phone, avatar_url, is_builder, is_admin, is_active,
                  first_name, age_range, city, country, dust_balance, auth_provider,
                  last_profiling_session, total_profiling_sessions, streak_days, last_login_date,
                  created_at, updated_at
           FROM users WHERE id = $1""",
        current_user.user_id,
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return User(**user)


@user_router.patch("/me", response_model=User)
async def update_user_profile(
    update_data: UserUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
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
            update_data.fairyname,
            current_user.user_id,
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
async def get_user_public_profile(user_id: str, db: Database = Depends(get_db)):
    """Get public user profile"""
    user = await db.fetch_one(
        """
        SELECT id, fairyname, avatar_url, is_builder, created_at
        FROM users
        WHERE id = $1 AND is_active = true
        """,
        user_id,
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserPublic(**user)


# Progressive Profiling Routes


@user_router.get("/{user_id}/profile-data", response_model=list[UserProfileData])
async def get_user_profile_data(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    category: Optional[str] = None,
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


@user_router.patch("/{user_id}/profile-data", response_model=list[UserProfileData])
async def update_user_profile_data(
    user_id: str,
    profile_batch: ProfileDataBatch,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
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
            user_id,
            profile_data.field_name,
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
                field_value_json,
                profile_data.confidence_score,
                profile_data.source,
                profile_data.app_context,
                profile_data.category,
                user_id,
                profile_data.field_name,
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
                user_id,
                profile_data.category,
                profile_data.field_name,
                field_value_json,
                profile_data.confidence_score,
                profile_data.source,
                profile_data.app_context,
            )

        updated_data.append(UserProfileData(**updated))

    return updated_data


@user_router.post("/{user_id}/people", response_model=PersonInMyLife)
async def add_person_to_life(
    user_id: str,
    person: PersonInMyLifeCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
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
        user_id,
        person.name,
        person.age_range,
        person.relationship,
    )

    return PersonInMyLife(**new_person)


@user_router.get("/{user_id}/people", response_model=list[PersonInMyLife])
async def get_people_in_my_life(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get all people in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    people = await db.fetch_all(
        "SELECT * FROM people_in_my_life WHERE user_id = $1 ORDER BY created_at ASC", user_id
    )

    return [PersonInMyLife(**person) for person in people]


@user_router.patch("/{user_id}/people/{person_id}", response_model=PersonInMyLife)
async def update_person_in_my_life(
    user_id: str,
    person_id: str,
    person_update: PersonInMyLifeUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user
    existing = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2", person_id, user_id
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
    db: Database = Depends(get_db),
):
    """Remove person from user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user before deletion
    existing = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2", person_id, user_id
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")

    await db.execute("DELETE FROM people_in_my_life WHERE id = $1", person_id)

    return {"message": "Person removed successfully"}


@user_router.post("/{user_id}/people/{person_id}/profile-data", response_model=PersonProfileData)
async def add_person_profile_data(
    user_id: str,
    person_id: str,
    profile_data: PersonProfileDataCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Add profile data for person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user
    person = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2", person_id, user_id
    )

    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # Serialize field_value for JSONB storage
    field_value_json = json.dumps(profile_data.field_value)

    # Upsert person profile data
    existing = await db.fetch_one(
        "SELECT id FROM person_profile_data WHERE person_id = $1 AND field_name = $2",
        person_id,
        profile_data.field_name,
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
            field_value_json,
            profile_data.confidence_score,
            profile_data.source,
            profile_data.category,
            person_id,
            profile_data.field_name,
        )
    else:
        updated = await db.fetch_one(
            """
            INSERT INTO person_profile_data
            (person_id, user_id, category, field_name, field_value, confidence_score, source)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            RETURNING *
            """,
            person_id,
            user_id,
            profile_data.category,
            profile_data.field_name,
            field_value_json,
            profile_data.confidence_score,
            profile_data.source,
        )

    return PersonProfileData(**updated)


@user_router.get(
    "/{user_id}/people/{person_id}/profile-data", response_model=list[PersonProfileData]
)
async def get_person_profile_data(
    user_id: str,
    person_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get profile data for person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user
    person = await db.fetch_one(
        "SELECT id FROM people_in_my_life WHERE id = $1 AND user_id = $2", person_id, user_id
    )

    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    profile_data = await db.fetch_all(
        "SELECT * FROM person_profile_data WHERE person_id = $1 ORDER BY updated_at DESC", person_id
    )

    return [PersonProfileData(**data) for data in profile_data]





@user_router.post("/{user_id}/migrate-local-data")
async def migrate_local_data(
    user_id: str,
    local_data: LocalProfileData,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Migrate local profile data to backend"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    migrated_items = {"profile_fields": 0, "people": 0}

    profile = local_data.profile

    # Helper function to convert age to age_range
    def age_to_range(age):
        if age <= 2:
            return "infant"
        elif age <= 5:
            return "toddler"
        elif age <= 12:
            return "child"
        elif age <= 17:
            return "teen"
        elif age <= 25:
            return "young_adult"
        elif age <= 40:
            return "adult"
        elif age <= 60:
            return "middle_aged"
        else:
            return "senior"

    # Update basic profile fields that go in users table
    basic_fields = ["first_name", "age_range", "city", "country"]
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
            *values,
        )

    # Migrate progressive profiling fields
    profile_field_mapping = {
        "interests": ("interests", "interests"),
        "dietary_preferences": ("cooking", "dietary_preferences"),
        "cooking_skill_level": ("cooking", "cooking_skill_level"),
        "lifestyle_goals": ("goals", "lifestyle_goals"),
        "personality_traits": ("personality", "personality_traits"),
        "adventure_level": ("personality", "adventure_level"),
        "creativity_level": ("personality", "creativity_level"),
        "social_preference": ("personality", "social_preference"),
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
                user_id,
                category,
                profile_field,
                field_value_json,
            )
            migrated_items["profile_fields"] += 1

    # Migrate people in my life
    for person_data in local_data.people_in_my_life:
        name = person_data.get("name")
        age = person_data.get("age")
        relationship = person_data.get("relationship")

        if not name:
            continue

        # Convert age to age_range
        age_range = age_to_range(age) if age else None

        # Check if person already exists
        existing_person = await db.fetch_one(
            "SELECT id FROM people_in_my_life WHERE user_id = $1 AND name = $2", user_id, name
        )

        if not existing_person:
            await db.execute(
                """
                INSERT INTO people_in_my_life (user_id, name, age_range, relationship)
                VALUES ($1, $2, $3, $4)
                """,
                user_id,
                name,
                age_range,
                relationship,
            )
            migrated_items["people"] += 1



    return {
        "success": True,
        "migrated": migrated_items,
        "message": f"Successfully migrated {sum(migrated_items.values())} items",
    }


