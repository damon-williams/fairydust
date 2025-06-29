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
    OAuthCallback,
    OTPRequest,
    OTPVerify,
    PersonInMyLife,
    PersonInMyLifeCreate,
    PersonInMyLifeUpdate,
    RefreshTokenRequest,
    Token,
    User,
    UserPublic,
    UserUpdate,
)

from shared.database import Database, get_db
from shared.email_service import send_otp_email
from shared.redis_client import get_redis
from shared.sms_service import send_otp_sms
from shared.streak_utils import calculate_daily_streak

security = HTTPBearer()

# Constants
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
                  is_onboarding_completed, first_name, age_range, city, country, dust_balance, auth_provider,
                  last_profiling_session, total_profiling_sessions, streak_days, last_login_date,
                  created_at, updated_at
           FROM users WHERE {identifier_type} = $1""",
        otp_verify.identifier,
    )

    is_new_user = False

    if not user:
        # Create new user
        is_new_user = True

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
            0,  # Starting balance is 0, app will handle initial grants
            "otp",
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
        dust_granted=0,  # DUST grants now handled by apps, not identity service
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

    if not user:
        # Create new user
        is_new_user = True

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
            0,  # Starting balance is 0, app will handle initial grants
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
        dust_granted=0,  # DUST grants now handled by apps, not identity service
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
                  is_onboarding_completed, first_name, age_range, city, country, dust_balance, auth_provider,
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
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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


# Profile data endpoints removed - no longer needed


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


# Person profile data endpoints removed - no longer needed


# Local data migration endpoint removed - no longer needed
