import secrets
import string
from datetime import datetime
from uuid import uuid4

from auth import AuthService, TokenData, get_current_user
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from models import (
    AuthResponse,
    OAuthCallback,
    OnboardTracking,
    OnboardTrackingUpdate,
    OTPRequest,
    OTPVerify,
    PersonInMyLife,
    PersonInMyLifeCreate,
    PersonInMyLifeUpdate,
    ReferralCodeResponse,
    RefreshTokenRequest,
    Token,
    User,
    UserUpdate,
)

from shared.database import Database, get_db
from shared.email_service import send_otp_email
from shared.redis_client import get_redis
from shared.sms_service import send_otp_sms
from shared.streak_utils import calculate_daily_streak_for_auth

security = HTTPBearer()

# Constants
FAIRYNAME_LENGTH = 12

# Create routers
auth_router = APIRouter()
user_router = APIRouter()


def generate_fairyname() -> str:
    """Generate a unique fairyname for new users"""
    # Expanded whimsical word lists for more variety
    adjectives = [
        # Mystical/Magic
        "crystal", "lunar", "stellar", "mystic", "cosmic", "ethereal", "radiant", "twilight",
        "enchanted", "magical", "celestial", "divine", "arcane", "mystical", "sacred", "ethereal",
        "luminous", "shimmering", "iridescent", "opalescent", "glowing", "sparkling",
        
        # Nature/Elements
        "golden", "silver", "emerald", "sapphire", "ruby", "diamond", "amber", "pearl",
        "forest", "ocean", "mountain", "desert", "winter", "spring", "summer", "autumn",
        "stormy", "sunny", "cloudy", "misty", "frosty", "dewy", "breezy", "gentle",
        
        # Emotions/Qualities  
        "serene", "peaceful", "joyful", "cheerful", "brave", "kind", "wise", "clever",
        "swift", "graceful", "elegant", "charming", "vibrant", "lively", "spirited", "bold",
        "dreamy", "whimsical", "playful", "curious", "adventurous", "creative", "artistic",
        
        # Fantasy/Ethereal
        "fairy", "sprite", "pixie", "angel", "phoenix", "dragon", "unicorn", "pegasus",
        "starlight", "moonbeam", "sunray", "rainbow", "aurora", "nebula", "comet", "galaxy"
    ]
    
    nouns = [
        # Natural elements
        "spark", "dream", "wish", "star", "moon", "light", "dawn", "dusk",
        "flame", "ember", "glow", "shine", "beam", "ray", "gleam", "shimmer",
        "breeze", "whisper", "echo", "song", "melody", "harmony", "rhythm", "dance",
        
        # Magical/Fantasy
        "wand", "spell", "charm", "potion", "crystal", "gem", "jewel", "treasure",
        "feather", "wing", "flight", "soar", "glide", "float", "drift", "flow",
        "blossom", "petal", "bloom", "garden", "meadow", "grove", "haven", "sanctuary",
        
        # Abstract concepts
        "spirit", "soul", "heart", "mind", "essence", "aura", "vibe", "energy",
        "journey", "quest", "adventure", "discovery", "wonder", "mystery", "secret", "riddle",
        "joy", "bliss", "peace", "calm", "zen", "balance", "harmony", "grace",
        
        # Celestial
        "nova", "quasar", "orbit", "cosmos", "void", "infinity", "eternity", "horizon",
        "eclipse", "solstice", "equinox", "constellation", "meteorite", "asteroid", "planet"
    ]

    adj = secrets.choice(adjectives)
    noun = secrets.choice(nouns)
    suffix = "".join(secrets.choice(string.digits) for _ in range(4))

    return f"{adj}{noun}{suffix}"


def generate_referral_code() -> str:
    """Generate a unique referral code for users"""
    # Use "FAIRY" prefix followed by 3 random digits
    code = "FAIRY" + "".join(secrets.choice(string.digits) for _ in range(3))
    return code


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
        f"""SELECT id, fairyname, email, phone, is_admin,
                  first_name, birth_date, is_onboarding_completed, dust_balance, auth_provider,
                  streak_days, last_login_date,
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
    (
        streak_days,
        last_login_date,
        is_bonus_eligible,
        current_streak_day,
    ) = await calculate_daily_streak_for_auth(
        db, str(user["id"]), user.get("streak_days", 0), user.get("last_login_date")
    )

    # Note: Database is NOT updated in auth - only calculated for response
    # DUST grant endpoint will handle actual database updates

    # Create tokens
    token_data = {
        "user_id": str(user["id"]),
        "fairyname": user["fairyname"],
        "is_admin": user.get("is_admin", False),
    }

    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)

    return AuthResponse(
        user=User(**user),
        token=Token(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        is_new_user=is_new_user,
        dust_granted=0,  # DUST grants now handled by apps, not identity service
        is_first_login_today=is_bonus_eligible,
        streak_bonus_eligible=not is_new_user and is_bonus_eligible and user.get("is_onboarding_completed", False),
        current_streak_day=current_streak_day,
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
            INSERT INTO users (id, fairyname, email, dust_balance, auth_provider)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            user_id,
            fairyname,
            user_info.get("email"),
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
    (
        streak_days,
        last_login_date,
        is_bonus_eligible,
        current_streak_day,
    ) = await calculate_daily_streak_for_auth(
        db, str(user["id"]), user.get("streak_days", 0), user.get("last_login_date")
    )

    # Note: Database is NOT updated in auth - only calculated for response
    # DUST grant endpoint will handle actual database updates

    # Create tokens
    token_data = {
        "user_id": str(user["id"]),
        "fairyname": user["fairyname"],
        "is_admin": user.get("is_admin", False),
    }

    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)

    return AuthResponse(
        user=User(**user),
        token=Token(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        is_new_user=is_new_user,
        dust_granted=0,  # DUST grants now handled by apps, not identity service
        is_first_login_today=is_bonus_eligible,
        streak_bonus_eligible=not is_new_user and is_bonus_eligible and user.get("is_onboarding_completed", False),
        current_streak_day=current_streak_day,
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
        "is_admin": token_data.is_admin,
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
        """SELECT id, fairyname, email, phone, is_admin,
                  first_name, birth_date, is_onboarding_completed, dust_balance, auth_provider,
                  streak_days, last_login_date,
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

    if update_data.first_name is not None:
        updates.append(f"first_name = ${param_count}")
        values.append(update_data.first_name)
        param_count += 1

    if update_data.birth_date is not None:
        updates.append(f"birth_date = ${param_count}")
        # Convert string date to Python date object for PostgreSQL DATE column
        try:
            birth_date_obj = datetime.strptime(update_data.birth_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birth_date format. Use YYYY-MM-DD")
        values.append(birth_date_obj)
        param_count += 1

    if update_data.is_onboarding_completed is not None:
        print(
            f"🔄 USER_UPDATE: Updating is_onboarding_completed to {update_data.is_onboarding_completed} for user {current_user.user_id}",
            flush=True,
        )
        updates.append(f"is_onboarding_completed = ${param_count}")
        values.append(update_data.is_onboarding_completed)
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

    # Log the result after update
    print(
        f"✅ USER_UPDATE: Updated user {current_user.user_id} - is_onboarding_completed: {user.get('is_onboarding_completed')}",
        flush=True,
    )

    return User(**user)


# Onboard Tracking Routes
@user_router.get("/me/onboard-test")
async def test_onboard_route():
    """Test route to verify routing is working"""
    return {"message": "onboard route accessible", "timestamp": "2025-06-29"}


@user_router.get("/me/onboard", response_model=OnboardTracking)
async def get_user_onboard_tracking(
    current_user: TokenData = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Get current user's onboard tracking state"""
    print(
        f"🔄 ONBOARD_TRACKING: Getting onboard tracking for user {current_user.user_id}", flush=True
    )

    tracking = await db.fetch_one(
        "SELECT * FROM user_onboard_tracking WHERE user_id = $1",
        current_user.user_id,
    )

    if not tracking:
        # Create default tracking record if it doesn't exist
        print(
            f"📝 ONBOARD_TRACKING: Creating new tracking record for user {current_user.user_id}",
            flush=True,
        )
        try:
            tracking = await db.fetch_one(
                """
                INSERT INTO user_onboard_tracking (user_id)
                VALUES ($1)
                RETURNING *
                """,
                current_user.user_id,
            )
            print("✅ ONBOARD_TRACKING: Created tracking record successfully", flush=True)
        except Exception as e:
            print(f"❌ ONBOARD_TRACKING: Error creating tracking record: {str(e)}", flush=True)
            raise HTTPException(status_code=500, detail="Failed to create onboard tracking record")
    else:
        print("✅ ONBOARD_TRACKING: Found existing tracking record", flush=True)

    print(
        f"📤 ONBOARD_TRACKING: Returning tracking data for user {current_user.user_id}", flush=True
    )
    return OnboardTracking(**tracking)


@user_router.patch("/me/onboard", response_model=OnboardTracking)
async def update_user_onboard_tracking(
    update_data: OnboardTrackingUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update current user's onboard tracking state"""
    # Build update query dynamically
    updates = []
    values = []
    param_count = 1

    if update_data.has_used_inspire is not None:
        updates.append(f"has_used_inspire = ${param_count}")
        values.append(update_data.has_used_inspire)
        param_count += 1

    if update_data.has_completed_first_inspiration is not None:
        updates.append(f"has_completed_first_inspiration = ${param_count}")
        values.append(update_data.has_completed_first_inspiration)
        param_count += 1

    if update_data.onboarding_step is not None:
        updates.append(f"onboarding_step = ${param_count}")
        values.append(update_data.onboarding_step)
        param_count += 1

    if update_data.has_seen_inspire_tip is not None:
        updates.append(f"has_seen_inspire_tip = ${param_count}")
        values.append(update_data.has_seen_inspire_tip)
        param_count += 1

    if update_data.has_seen_inspire_result_tip is not None:
        updates.append(f"has_seen_inspire_result_tip = ${param_count}")
        values.append(update_data.has_seen_inspire_result_tip)
        param_count += 1

    if update_data.has_seen_onboarding_complete_tip is not None:
        updates.append(f"has_seen_onboarding_complete_tip = ${param_count}")
        values.append(update_data.has_seen_onboarding_complete_tip)
        param_count += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Add user_id as last parameter
    values.append(current_user.user_id)

    # Use UPSERT (INSERT ... ON CONFLICT) to handle case where record doesn't exist yet
    upsert_query = f"""
        INSERT INTO user_onboard_tracking (user_id)
        VALUES (${param_count})
        ON CONFLICT (user_id)
        DO UPDATE SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """

    tracking = await db.fetch_one(upsert_query, *values)
    if not tracking:
        raise HTTPException(status_code=500, detail="Failed to update onboard tracking")

    return OnboardTracking(**tracking)


# Progressive Profiling Routes


# Public profile and profile data endpoints removed - no longer needed


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

    # Convert birth_date string to date object if provided
    birth_date_obj = None
    if person.birth_date:
        try:
            birth_date_obj = datetime.strptime(person.birth_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birth_date format. Use YYYY-MM-DD")

    new_person = await db.fetch_one(
        """
        INSERT INTO people_in_my_life (user_id, name, birth_date, relationship)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        user_id,
        person.name,
        birth_date_obj,
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

    if person_update.birth_date is not None:
        updates.append(f"birth_date = ${param_count}")
        # Convert string date to Python date object for PostgreSQL DATE column
        try:
            birth_date_obj = datetime.strptime(person_update.birth_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birth_date format. Use YYYY-MM-DD")
        values.append(birth_date_obj)
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


# Referral Code Routes
@user_router.post("/{user_id}/referral-code", response_model=ReferralCodeResponse)
async def create_referral_code(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Generate new referral code for user"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if user already has an active referral code
    existing_code = await db.fetch_one(
        """
        SELECT * FROM referral_codes 
        WHERE user_id = $1 AND is_active = true AND expires_at > CURRENT_TIMESTAMP
        """,
        user_id,
    )

    if existing_code:
        return ReferralCodeResponse(**existing_code)

    # Deactivate any existing codes for this user
    await db.execute(
        "UPDATE referral_codes SET is_active = false WHERE user_id = $1",
        user_id,
    )

    # Generate new unique code
    max_retries = 10
    for _ in range(max_retries):
        code = generate_referral_code()
        
        # Check if code already exists
        existing = await db.fetch_one(
            "SELECT id FROM referral_codes WHERE referral_code = $1", code
        )
        
        if not existing:
            break
    else:
        # If we couldn't find unique code after 10 tries, add timestamp
        import time
        code = f"FAIRY{int(time.time() % 1000):03d}"

    # Set expiry to 30 days from now (configurable later via admin)
    from datetime import timedelta
    expires_at = datetime.now() + timedelta(days=30)

    # Create new referral code
    new_code = await db.fetch_one(
        """
        INSERT INTO referral_codes (user_id, referral_code, expires_at)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        user_id,
        code,
        expires_at,
    )

    return ReferralCodeResponse(**new_code)


@user_router.get("/{user_id}/referral-code", response_model=ReferralCodeResponse)
async def get_referral_code(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get user's active referral code"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get active referral code
    code = await db.fetch_one(
        """
        SELECT * FROM referral_codes 
        WHERE user_id = $1 AND is_active = true AND expires_at > CURRENT_TIMESTAMP
        ORDER BY created_at DESC
        LIMIT 1
        """,
        user_id,
    )

    if not code:
        raise HTTPException(status_code=404, detail="No active referral code found")

    return ReferralCodeResponse(**code)


# Local data migration endpoint removed - no longer needed
