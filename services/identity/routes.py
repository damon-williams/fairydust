import json
import secrets
import string
from datetime import datetime
from typing import Optional
from uuid import uuid4

from auth import AuthService, TokenData, get_current_user
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Security,
    UploadFile,
)
from fastapi.security import HTTPBearer
from models import (
    AccountDeletionRequest,
    AccountDeletionResponse,
    AuthResponse,
    OAuthCallback,
    OnboardTracking,
    OnboardTrackingUpdate,
    OTPRequest,
    OTPVerify,
    PersonInMyLife,
    PersonInMyLifeCreate,
    PersonInMyLifeUpdate,
    PublicTermsResponse,
    ReferralCodeResponse,
    RefreshTokenRequest,
    SingleTermsResponse,
    TermsAcceptanceRequest,
    TermsCheckResponse,
    TermsDocument,
    Token,
    User,
    UserTermsAcceptance,
    UserUpdate,
)

from shared.daily_bonus_utils import check_daily_bonus_eligibility
from shared.database import Database, get_db
from shared.email_service import send_account_deletion_confirmation, send_otp_email
from shared.hubspot_webhook import send_user_created_webhook, send_user_updated_webhook
from shared.redis_client import get_redis
from shared.sms_service import send_otp_sms
from shared.storage_service import (
    delete_person_photo,
    delete_user_assets,
    delete_user_avatar,
    upload_person_photo,
    upload_user_avatar,
)


async def get_daily_bonus_amount(db: Database) -> int:
    """Get current daily bonus amount from system config with fallback"""
    try:
        config_result = await db.fetch_one(
            "SELECT value FROM system_config WHERE key = 'daily_login_bonus_amount'"
        )
        if config_result:
            return int(config_result["value"])
    except Exception:
        pass
    return 5  # Default fallback


async def get_initial_dust_amount(db: Database) -> int:
    """Get current initial dust amount from system config with fallback"""
    try:
        config_result = await db.fetch_one(
            "SELECT value FROM system_config WHERE key = 'initial_dust_amount'"
        )
        if config_result:
            return int(config_result["value"])
    except Exception:
        pass
    return 100  # Default fallback


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
        "crystal",
        "lunar",
        "stellar",
        "mystic",
        "cosmic",
        "ethereal",
        "radiant",
        "twilight",
        "enchanted",
        "magical",
        "celestial",
        "divine",
        "arcane",
        "mystical",
        "sacred",
        "ethereal",
        "luminous",
        "shimmering",
        "iridescent",
        "opalescent",
        "glowing",
        "sparkling",
        # Nature/Elements
        "golden",
        "silver",
        "emerald",
        "sapphire",
        "ruby",
        "diamond",
        "amber",
        "pearl",
        "forest",
        "ocean",
        "mountain",
        "desert",
        "winter",
        "spring",
        "summer",
        "autumn",
        "stormy",
        "sunny",
        "cloudy",
        "misty",
        "frosty",
        "dewy",
        "breezy",
        "gentle",
        # Emotions/Qualities
        "serene",
        "peaceful",
        "joyful",
        "cheerful",
        "brave",
        "kind",
        "wise",
        "clever",
        "swift",
        "graceful",
        "elegant",
        "charming",
        "vibrant",
        "lively",
        "spirited",
        "bold",
        "dreamy",
        "whimsical",
        "playful",
        "curious",
        "adventurous",
        "creative",
        "artistic",
        # Fantasy/Ethereal
        "fairy",
        "sprite",
        "pixie",
        "angel",
        "phoenix",
        "dragon",
        "unicorn",
        "pegasus",
        "starlight",
        "moonbeam",
        "sunray",
        "rainbow",
        "aurora",
        "nebula",
        "comet",
        "galaxy",
    ]

    nouns = [
        # Natural elements
        "spark",
        "dream",
        "wish",
        "star",
        "moon",
        "light",
        "dawn",
        "dusk",
        "flame",
        "ember",
        "glow",
        "shine",
        "beam",
        "ray",
        "gleam",
        "shimmer",
        "breeze",
        "whisper",
        "echo",
        "song",
        "melody",
        "harmony",
        "rhythm",
        "dance",
        # Magical/Fantasy
        "wand",
        "spell",
        "charm",
        "potion",
        "crystal",
        "gem",
        "jewel",
        "treasure",
        "feather",
        "wing",
        "flight",
        "soar",
        "glide",
        "float",
        "drift",
        "flow",
        "blossom",
        "petal",
        "bloom",
        "garden",
        "meadow",
        "grove",
        "haven",
        "sanctuary",
        # Abstract concepts
        "spirit",
        "soul",
        "heart",
        "mind",
        "essence",
        "aura",
        "vibe",
        "energy",
        "journey",
        "quest",
        "adventure",
        "discovery",
        "wonder",
        "mystery",
        "secret",
        "riddle",
        "joy",
        "bliss",
        "peace",
        "calm",
        "zen",
        "balance",
        "harmony",
        "grace",
        # Celestial
        "nova",
        "quasar",
        "orbit",
        "cosmos",
        "void",
        "infinity",
        "eternity",
        "horizon",
        "eclipse",
        "solstice",
        "equinox",
        "constellation",
        "meteorite",
        "asteroid",
        "planet",
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
                  last_login_date,
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

        # Send HubSpot webhook for new user (non-blocking)
        try:
            await send_user_created_webhook(dict(user))
        except Exception as e:
            # Log error but don't block user registration
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"HubSpot webhook failed for new user {user['fairyname']}: {e}")

    # Check daily login bonus eligibility
    is_bonus_eligible, current_time = await check_daily_bonus_eligibility(
        db, str(user["id"]), user.get("last_login_date")
    )

    # Note: Database is NOT updated in auth - only checked for response
    # DUST grant endpoint will handle actual database updates

    # Get daily bonus amount from system config
    daily_bonus_amount = await get_daily_bonus_amount(db)

    # Get initial dust amount from system config
    initial_dust_amount = await get_initial_dust_amount(db)

    # Add calculated daily bonus fields to user data
    user_dict = dict(user)
    daily_bonus_value = (
        not is_new_user and is_bonus_eligible and user.get("is_onboarding_completed", False)
    )
    user_dict["daily_bonus_eligible"] = daily_bonus_value
    user_dict["daily_bonus_amount"] = daily_bonus_amount
    user_dict["initial_dust_amount"] = initial_dust_amount

    # Create tokens
    token_data = {
        "user_id": str(user["id"]),
        "fairyname": user["fairyname"],
        "email": user.get("email"),
        "is_admin": user.get("is_admin", False),
    }

    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)

    return AuthResponse(
        user=User(**user_dict),
        token=Token(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        is_new_user=is_new_user,
        dust_granted=0,  # DUST grants now handled by apps, not identity service
        is_first_login_today=is_bonus_eligible,
        daily_bonus_eligible=daily_bonus_value,
    )


@auth_router.post("/oauth/{provider}", response_model=AuthResponse)
async def oauth_login(
    provider: str,
    callback: OAuthCallback,
    db: Database = Depends(get_db),
    auth_service: AuthService = Depends(lambda r=Depends(get_redis): AuthService(r)),
):
    """Handle OAuth callback and create/login user"""

    # Handle native Apple Sign-In (mobile apps) - prioritize this for Apple
    if provider == "apple" and callback.id_token:
        # Native flow - ID token provided directly (prioritize over code for Apple)
        print("📱 APPLE: Native Sign-In flow detected (ID token provided)")
        access_token = None  # Not used in native flow
        id_token = callback.id_token
        apple_user_data = callback.user

    # Handle web OAuth flows (including web Apple Sign-In)
    elif callback.code:
        # Web OAuth flow - exchange code for tokens
        print(f"🌐 {provider.upper()}: Web OAuth flow detected (authorization code provided)")
        token_response = await auth_service.get_oauth_token(provider, callback.code)
        access_token = token_response.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        id_token = token_response.get("id_token") if provider == "apple" else None
        apple_user_data = callback.user if provider == "apple" else None

    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'code' (web OAuth) or 'id_token' (native Apple Sign-In) must be provided",
        )

    # Get user info from provider
    user_info = await auth_service.get_oauth_user_info(
        provider, access_token, id_token, apple_user_data
    )

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
        # Check if user exists with this email (for account linking)
        existing_user = await db.fetch_one(
            "SELECT * FROM users WHERE email = $1", user_info.get("email")
        )

        if existing_user:
            # Link OAuth provider to existing user account
            print(
                f"🔗 OAUTH: Linking {provider} to existing user account with email {user_info.get('email')}"
            )

            # Check if this OAuth provider is already linked
            existing_link = await db.fetch_one(
                "SELECT * FROM user_auth_providers WHERE user_id = $1 AND provider = $2",
                existing_user["id"],
                provider,
            )

            if not existing_link:
                # Link the OAuth provider to existing user
                await db.execute(
                    """
                    INSERT INTO user_auth_providers (user_id, provider, provider_user_id)
                    VALUES ($1, $2, $3)
                    """,
                    existing_user["id"],
                    provider,
                    user_info["provider_id"],
                )
                print(
                    f"✅ OAUTH: Successfully linked {provider} to existing user {existing_user['fairyname']}"
                )
            else:
                print(f"ℹ️ OAUTH: {provider} already linked to user {existing_user['fairyname']}")

            user = existing_user
            is_new_user = False
        else:
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

            print(f"👤 OAUTH: Created new user {fairyname} with {provider} authentication")

            # Send HubSpot webhook for new user (non-blocking)
            try:
                await send_user_created_webhook(dict(user))
            except Exception as e:
                # Log error but don't block user registration
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"HubSpot webhook failed for new OAuth user {user['fairyname']}: {e}"
                )

    # Check daily login bonus eligibility
    is_bonus_eligible, current_time = await check_daily_bonus_eligibility(
        db, str(user["id"]), user.get("last_login_date")
    )

    # Note: Database is NOT updated in auth - only checked for response
    # DUST grant endpoint will handle actual database updates

    # Get daily bonus amount from system config
    daily_bonus_amount = await get_daily_bonus_amount(db)

    # Get initial dust amount from system config
    initial_dust_amount = await get_initial_dust_amount(db)

    # Add calculated daily bonus fields to user data
    user_dict = dict(user)
    daily_bonus_value = (
        not is_new_user and is_bonus_eligible and user.get("is_onboarding_completed", False)
    )
    user_dict["daily_bonus_eligible"] = daily_bonus_value
    user_dict["daily_bonus_amount"] = daily_bonus_amount
    user_dict["initial_dust_amount"] = initial_dust_amount

    # Create tokens
    token_data = {
        "user_id": str(user["id"]),
        "fairyname": user["fairyname"],
        "email": user.get("email"),
        "is_admin": user.get("is_admin", False),
    }

    access_token = await auth_service.create_access_token(token_data)
    refresh_token = await auth_service.create_refresh_token(token_data)

    return AuthResponse(
        user=User(**user_dict),
        token=Token(access_token=access_token, refresh_token=refresh_token, expires_in=3600),
        is_new_user=is_new_user,
        dust_granted=0,  # DUST grants now handled by apps, not identity service
        is_first_login_today=is_bonus_eligible,
        daily_bonus_eligible=daily_bonus_value,
        extracted_name=user_info.get("name") if user_info else None,
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
    if not stored_token or stored_token != request.refresh_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Create new access token
    new_token_data = {
        "user_id": token_data.user_id,
        "fairyname": token_data.fairyname,
        "email": token_data.email,
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
                  last_login_date, avatar_url, avatar_uploaded_at, avatar_size_bytes,
                  created_at, updated_at
           FROM users WHERE id = $1""",
        current_user.user_id,
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check daily bonus eligibility for frontend
    is_bonus_eligible, current_time = await check_daily_bonus_eligibility(
        db, str(user["id"]), user.get("last_login_date")
    )

    # Get daily bonus amount from system config
    daily_bonus_amount = await get_daily_bonus_amount(db)

    # Get initial dust amount from system config
    initial_dust_amount = await get_initial_dust_amount(db)

    # Convert user dict to mutable dict and add calculated fields
    user_dict = dict(user)
    user_dict["daily_bonus_eligible"] = is_bonus_eligible
    user_dict["daily_bonus_amount"] = daily_bonus_amount
    user_dict["initial_dust_amount"] = initial_dust_amount

    return User(**user_dict)


@user_router.patch("/me", response_model=User)
async def update_user_profile(
    update_data: UserUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update current user profile"""
    # Track changed fields for HubSpot webhook
    changed_fields = []

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
        changed_fields.append("fairyname")
        param_count += 1

    if update_data.email is not None:
        updates.append(f"email = ${param_count}")
        values.append(update_data.email)
        changed_fields.append("email")
        param_count += 1

    if update_data.phone is not None:
        updates.append(f"phone = ${param_count}")
        values.append(update_data.phone)
        changed_fields.append("phone")
        param_count += 1

    if update_data.first_name is not None:
        updates.append(f"first_name = ${param_count}")
        values.append(update_data.first_name)
        changed_fields.append("first_name")
        param_count += 1

    if update_data.birth_date is not None:
        updates.append(f"birth_date = ${param_count}")
        # Convert string date to Python date object for PostgreSQL DATE column
        try:
            birth_date_obj = datetime.strptime(update_data.birth_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birth_date format. Use YYYY-MM-DD")
        values.append(birth_date_obj)
        changed_fields.append("birth_date")
        param_count += 1

    if update_data.is_onboarding_completed is not None:
        print(
            f"🔄 USER_UPDATE: Updating is_onboarding_completed to {update_data.is_onboarding_completed} for user {current_user.user_id}",
            flush=True,
        )
        updates.append(f"is_onboarding_completed = ${param_count}")
        values.append(update_data.is_onboarding_completed)
        changed_fields.append("is_onboarding_completed")
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

    # Send HubSpot webhook for user update (non-blocking)
    if changed_fields:  # Only send if there were actual changes
        try:
            await send_user_updated_webhook(dict(user), changed_fields)
        except Exception as e:
            # Log error but don't block user update
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"HubSpot webhook failed for user update {user['fairyname']}: {e}")

    return User(**user)


# User Avatar Routes
@user_router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Upload or replace user avatar"""
    try:
        # Get current user data to check for existing avatar
        user_data = await db.fetch_one(
            "SELECT avatar_url FROM users WHERE id = $1", current_user.user_id
        )

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete old avatar if exists
        if user_data["avatar_url"]:
            await delete_user_avatar(user_data["avatar_url"])

        # Upload new avatar
        avatar_url, file_size = await upload_user_avatar(file, str(current_user.user_id))

        # Update user record with new avatar info
        await db.execute(
            """
            UPDATE users
            SET avatar_url = $1, avatar_uploaded_at = CURRENT_TIMESTAMP, avatar_size_bytes = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
            """,
            avatar_url,
            file_size,
            current_user.user_id,
        )

        return {
            "message": "Avatar uploaded successfully",
            "avatar_url": avatar_url,
            "file_size": file_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")


@user_router.get("/me/avatar")
async def get_avatar_info(
    current_user: TokenData = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Get current user's avatar information"""
    try:
        user_data = await db.fetch_one(
            "SELECT avatar_url, avatar_uploaded_at, avatar_size_bytes FROM users WHERE id = $1",
            current_user.user_id,
        )

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        if not user_data["avatar_url"]:
            raise HTTPException(status_code=404, detail="No avatar found")

        return {
            "avatar_url": user_data["avatar_url"],
            "avatar_uploaded_at": user_data["avatar_uploaded_at"],
            "avatar_size_bytes": user_data["avatar_size_bytes"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get avatar info: {str(e)}")


@user_router.delete("/me/avatar")
async def delete_avatar(
    current_user: TokenData = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Delete user's current avatar"""
    try:
        # Get current avatar URL
        user_data = await db.fetch_one(
            "SELECT avatar_url FROM users WHERE id = $1", current_user.user_id
        )

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        if not user_data["avatar_url"]:
            raise HTTPException(status_code=404, detail="No avatar to delete")

        # Delete from storage
        deleted_from_storage = await delete_user_avatar(user_data["avatar_url"])

        # Clear avatar info from database
        await db.execute(
            """
            UPDATE users
            SET avatar_url = NULL, avatar_uploaded_at = NULL, avatar_size_bytes = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            current_user.user_id,
        )

        return {
            "message": "Avatar deleted successfully",
            "deleted_from_storage": deleted_from_storage,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Avatar deletion failed: {str(e)}")


@user_router.delete("/me", response_model=AccountDeletionResponse)
async def delete_account(
    request: AccountDeletionRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
    redis=Depends(get_redis),
):
    """Delete user's account permanently"""
    try:
        user_id = current_user.user_id

        # Get user data for logging before deletion
        user_data = await db.fetch_one(
            """SELECT fairyname, email, created_at, dust_balance,
                      avatar_url, avatar_uploaded_at, avatar_size_bytes
               FROM users WHERE id = $1""",
            user_id,
        )

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Gather data summary for audit log
        stats_queries = [
            ("recipes_created", "SELECT COUNT(*) as count FROM user_recipes WHERE user_id = $1"),
            ("stories_created", "SELECT COUNT(*) as count FROM user_stories WHERE user_id = $1"),
            ("images_generated", "SELECT COUNT(*) as count FROM user_images WHERE user_id = $1"),
            (
                "people_in_life",
                "SELECT COUNT(*) as count FROM people_in_my_life WHERE user_id = $1",
            ),
            (
                "total_transactions",
                "SELECT COUNT(*) as count FROM dust_transactions WHERE user_id = $1",
            ),
            ("referrals_made", "SELECT COUNT(*) as count FROM referral_codes WHERE user_id = $1"),
        ]

        data_summary = {
            "dust_balance": user_data["dust_balance"],
            "account_age_days": (
                datetime.utcnow().replace(tzinfo=None)
                - user_data["created_at"].replace(tzinfo=None)
            ).days
            if user_data["created_at"]
            else 0,
            "has_avatar": bool(user_data["avatar_url"]),
            "last_deletion_request": datetime.utcnow().isoformat(),
        }

        # Get counts for data summary
        for stat_name, query in stats_queries:
            try:
                result = await db.fetch_one(query, user_id)
                data_summary[stat_name] = result["count"] if result else 0
            except Exception:
                data_summary[stat_name] = 0

        # Create deletion log entry
        deletion_id = str(uuid4())
        await db.execute(
            """INSERT INTO account_deletion_logs
               (id, user_id, fairyname, email, deletion_reason, deletion_feedback,
                deleted_by, user_created_at, data_summary, deletion_requested_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)""",
            deletion_id,
            user_id,
            user_data["fairyname"],
            user_data["email"],
            request.reason,
            request.feedback,
            "self",
            user_data["created_at"],
            json.dumps(data_summary),
        )

        # Delete storage assets (avatars, people photos, generated images)
        storage_deletion_summary = await delete_user_assets(user_id)

        # Clear Redis data (sessions, rate limits, etc.)
        try:
            # Clear user sessions
            session_keys = await redis.keys(f"session:*:{user_id}")
            if session_keys:
                await redis.delete(*session_keys)

            # Clear rate limiting data
            rate_limit_keys = await redis.keys(f"rate_limit:*:{user_id}*")
            if rate_limit_keys:
                await redis.delete(*rate_limit_keys)

            # Clear OTP codes
            otp_keys = await redis.keys(f"otp:*:{user_data['email']}*")
            if otp_keys:
                await redis.delete(*otp_keys)

        except Exception as e:
            # Log but don't fail deletion for Redis errors
            print(f"Redis cleanup warning for user {user_id}: {e}")

        # Delete user record (CASCADE will handle all related data)
        await db.execute("DELETE FROM users WHERE id = $1", user_id)

        # Update deletion log with completion
        await db.execute(
            """UPDATE account_deletion_logs
               SET deletion_completed_at = CURRENT_TIMESTAMP,
                   data_summary = data_summary || $2
               WHERE id = $1""",
            deletion_id,
            json.dumps({"storage_cleanup": storage_deletion_summary}),
        )

        # Send deletion confirmation email
        try:
            await send_account_deletion_confirmation(
                user_data["email"], user_data["fairyname"], deletion_id
            )
        except Exception as e:
            # Log email error but don't fail the deletion
            print(f"Email notification failed for user {user_id}: {e}")

        return AccountDeletionResponse(
            message="Account successfully deleted", deletion_id=deletion_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Account deletion failed: {str(e)}")


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
    tracking = await db.fetch_one(
        "SELECT * FROM user_onboard_tracking WHERE user_id = $1",
        current_user.user_id,
    )

    if not tracking:
        # Create default tracking record if it doesn't exist
        # Use INSERT ... ON CONFLICT to handle race conditions
        tracking = await db.fetch_one(
            """
            INSERT INTO user_onboard_tracking (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            current_user.user_id,
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
    """Add person or pet to user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Convert birth_date string to date object if provided
    birth_date_obj = None
    if person.birth_date:
        try:
            birth_date_obj = datetime.strptime(person.birth_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birth_date format. Use YYYY-MM-DD")

    print(f"🐾 PEOPLE_API: Adding {person.entry_type.value} '{person.name}' for user {user_id}")
    if person.entry_type.value == "pet":
        print(f"🐾 PEOPLE_API: Pet species: {person.species}")

    new_person = await db.fetch_one(
        """
        INSERT INTO people_in_my_life (user_id, name, entry_type, birth_date, relationship, species, personality_description)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        user_id,
        person.name,
        person.entry_type.value,
        birth_date_obj,
        person.relationship,
        person.species,
        person.personality_description,
    )

    return PersonInMyLife(**new_person)


@user_router.get("/{user_id}/people", response_model=list[PersonInMyLife])
async def get_people_in_my_life(
    user_id: str,
    type_filter: Optional[str] = Query(
        None, alias="type", description="Filter by type: 'person', 'pet', or omit for all"
    ),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get people and/or pets in user's life with optional type filtering"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Build query with optional type filtering
    if type_filter:
        if type_filter not in ["person", "pet"]:
            raise HTTPException(
                status_code=400, detail="Invalid type filter. Use 'person' or 'pet'"
            )

        print(f"🐾 PEOPLE_API: Filtering for {type_filter}s only for user {user_id}")
        people = await db.fetch_all(
            "SELECT * FROM people_in_my_life WHERE user_id = $1 AND entry_type = $2 ORDER BY created_at ASC",
            user_id,
            type_filter,
        )
    else:
        print(f"🐾 PEOPLE_API: Getting all people and pets for user {user_id}")
        people = await db.fetch_all(
            "SELECT * FROM people_in_my_life WHERE user_id = $1 ORDER BY created_at ASC", user_id
        )

    result = [PersonInMyLife(**person) for person in people]
    print(
        f"🐾 PEOPLE_API: Returning {len(result)} entries ({len([p for p in result if p.entry_type.value == 'person'])} people, {len([p for p in result if p.entry_type.value == 'pet'])} pets)"
    )

    return result


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

    if person_update.personality_description is not None:
        updates.append(f"personality_description = ${param_count}")
        values.append(person_update.personality_description)
        param_count += 1

    if person_update.entry_type is not None:
        updates.append(f"entry_type = ${param_count}")
        values.append(person_update.entry_type.value)
        param_count += 1

    if person_update.species is not None:
        updates.append(f"species = ${param_count}")
        values.append(person_update.species)
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


@user_router.post("/{user_id}/people/{person_id}/photo")
async def upload_person_photo_endpoint(
    user_id: str,
    person_id: str,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Upload a photo for a person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user
    existing = await db.fetch_one(
        "SELECT id, photo_url FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id,
        user_id,
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")

    try:
        # Upload new photo
        photo_url, file_size = await upload_person_photo(file, user_id, person_id)

        # Delete old photo if it exists
        if existing["photo_url"]:
            await delete_person_photo(existing["photo_url"])

        # Update database
        await db.execute(
            """UPDATE people_in_my_life
               SET photo_url = $1, photo_uploaded_at = CURRENT_TIMESTAMP,
                   photo_size_bytes = $2, updated_at = CURRENT_TIMESTAMP
               WHERE id = $3""",
            photo_url,
            file_size,
            person_id,
        )

        return {
            "message": "Photo uploaded successfully",
            "photo_url": photo_url,
            "file_size": file_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@user_router.get("/{user_id}/people/{person_id}/photo")
async def get_person_photo_endpoint(
    user_id: str,
    person_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get photo info for a person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get person with photo info
    person = await db.fetch_one(
        "SELECT photo_url, photo_uploaded_at, photo_size_bytes FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id,
        user_id,
    )

    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    if not person["photo_url"]:
        raise HTTPException(status_code=404, detail="No photo found")

    return {
        "photo_url": person["photo_url"],
        "photo_uploaded_at": person["photo_uploaded_at"],
        "photo_size_bytes": person["photo_size_bytes"],
    }


@user_router.patch("/{user_id}/people/{person_id}/photo")
async def update_person_photo_endpoint(
    user_id: str,
    person_id: str,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update/replace a photo for a person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user
    existing = await db.fetch_one(
        "SELECT id, photo_url FROM people_in_my_life WHERE id = $1 AND user_id = $2",
        person_id,
        user_id,
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")

    try:
        # Upload new photo
        photo_url, file_size = await upload_person_photo(file, user_id, person_id)

        # Delete old photo if it exists
        if existing["photo_url"]:
            await delete_person_photo(existing["photo_url"])

        # Update database
        await db.execute(
            """UPDATE people_in_my_life
               SET photo_url = $1, photo_uploaded_at = CURRENT_TIMESTAMP,
                   photo_size_bytes = $2, updated_at = CURRENT_TIMESTAMP
               WHERE id = $3""",
            photo_url,
            file_size,
            person_id,
        )

        return {
            "message": "Photo updated successfully",
            "photo_url": photo_url,
            "file_size": file_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@user_router.delete("/{user_id}/people/{person_id}/photo")
async def delete_person_photo_endpoint(
    user_id: str,
    person_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a photo for a person in user's life"""
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify person belongs to user and get photo URL
    existing = await db.fetch_one(
        "SELECT photo_url FROM people_in_my_life WHERE id = $1 AND user_id = $2", person_id, user_id
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Person not found")

    if not existing["photo_url"]:
        raise HTTPException(status_code=404, detail="No photo to delete")

    try:
        # Delete from R2
        deleted = await delete_person_photo(existing["photo_url"])

        # Update database (remove photo reference)
        await db.execute(
            """UPDATE people_in_my_life
               SET photo_url = NULL, photo_uploaded_at = NULL,
                   photo_size_bytes = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE id = $1""",
            person_id,
        )

        return {"message": "Photo deleted successfully", "deleted_from_storage": deleted}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


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


# Terms & Conditions Router
terms_router = APIRouter(prefix="/terms", tags=["terms"])


@terms_router.get("/check", response_model=TermsCheckResponse)
async def check_terms_acceptance(
    current_user: TokenData = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Check if user needs to accept new terms and conditions"""
    try:
        # Get currently active terms documents
        active_terms = await db.fetch_all(
            """
            SELECT * FROM terms_documents
            WHERE is_active = true AND requires_acceptance = true
            ORDER BY document_type, effective_date DESC
            """
        )

        if not active_terms:
            return TermsCheckResponse(requires_acceptance=False)

        # Get user's accepted terms
        user_acceptances = await db.fetch_all(
            """
            SELECT uta.*, td.document_type, td.version as document_version
            FROM user_terms_acceptance uta
            JOIN terms_documents td ON uta.document_id = td.id
            WHERE uta.user_id = $1
            ORDER BY uta.accepted_at DESC
            """,
            current_user.user_id,
        )

        # Find pending documents that require acceptance
        accepted_doc_ids = {acc["document_id"] for acc in user_acceptances}
        pending_documents = []

        for term_doc in active_terms:
            if term_doc["id"] not in accepted_doc_ids:
                pending_documents.append(TermsDocument(**term_doc))

        requires_acceptance = len(pending_documents) > 0

        # Convert user acceptances to response models
        acceptance_models = [UserTermsAcceptance(**acc) for acc in user_acceptances]

        return TermsCheckResponse(
            requires_acceptance=requires_acceptance,
            pending_documents=pending_documents,
            user_acceptances=acceptance_models,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check terms: {str(e)}")


@terms_router.post("/accept")
async def accept_terms(
    request: TermsAcceptanceRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Record user acceptance of specific terms document version"""
    try:
        # Get the specific document
        document = await db.fetch_one(
            """
            SELECT * FROM terms_documents
            WHERE document_type = $1 AND version = $2 AND is_active = true
            """,
            request.document_type,
            request.document_version,
        )

        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Terms document {request.document_type} v{request.document_version} not found or not active",
            )

        # Check if user already accepted this specific document
        existing_acceptance = await db.fetch_one(
            """
            SELECT id FROM user_terms_acceptance
            WHERE user_id = $1 AND document_id = $2
            """,
            current_user.user_id,
            document["id"],
        )

        if existing_acceptance:
            return {"message": "Terms already accepted", "acceptance_id": existing_acceptance["id"]}

        # Record the acceptance
        acceptance = await db.fetch_one(
            """
            INSERT INTO user_terms_acceptance (
                user_id, document_id, document_type, document_version,
                ip_address, user_agent, acceptance_method
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'voluntary')
            RETURNING *
            """,
            current_user.user_id,
            document["id"],
            request.document_type,
            request.document_version,
            request.ip_address,
            request.user_agent,
        )

        return {
            "message": "Terms accepted successfully",
            "acceptance_id": acceptance["id"],
            "accepted_at": acceptance["accepted_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record terms acceptance: {str(e)}")


@terms_router.get("/history", response_model=list[UserTermsAcceptance])
async def get_terms_history(
    current_user: TokenData = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Get user's terms acceptance history"""
    try:
        acceptances = await db.fetch_all(
            """
            SELECT uta.*, td.document_type, td.version as document_version
            FROM user_terms_acceptance uta
            JOIN terms_documents td ON uta.document_id = td.id
            WHERE uta.user_id = $1
            ORDER BY uta.accepted_at DESC
            """,
            current_user.user_id,
        )

        return [UserTermsAcceptance(**acc) for acc in acceptances]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch terms history: {str(e)}")


# Public Terms Router (no auth required)
public_terms_router = APIRouter(prefix="/public/terms", tags=["public-terms"])


@public_terms_router.get("/current")
async def get_current_terms(document_type: str = None, db: Database = Depends(get_db)):
    """Get current active terms documents (public endpoint)"""
    try:
        # Build query based on filter
        if document_type and document_type in ["terms_of_service", "privacy_policy"]:
            # Get specific document type
            document = await db.fetch_one(
                """
                SELECT * FROM terms_documents
                WHERE document_type = $1 AND is_active = true
                ORDER BY effective_date DESC
                LIMIT 1
                """,
                document_type,
            )

            if not document:
                raise HTTPException(status_code=404, detail=f"No active {document_type} found")

            return SingleTermsResponse(
                document=TermsDocument(**document), last_updated=document["created_at"]
            )

        else:
            # Get both document types
            terms_docs = await db.fetch_all(
                """
                SELECT DISTINCT ON (document_type) *
                FROM terms_documents
                WHERE is_active = true
                ORDER BY document_type, effective_date DESC
                """
            )

            terms_of_service = None
            privacy_policy = None
            latest_update = None

            for doc in terms_docs:
                doc_model = TermsDocument(**doc)
                if doc["document_type"] == "terms_of_service":
                    terms_of_service = doc_model
                elif doc["document_type"] == "privacy_policy":
                    privacy_policy = doc_model

                # Track latest update
                if latest_update is None or doc["created_at"] > latest_update:
                    latest_update = doc["created_at"]

            return PublicTermsResponse(
                terms_of_service=terms_of_service,
                privacy_policy=privacy_policy,
                last_updated=latest_update or datetime.now(),
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch current terms: {str(e)}")
