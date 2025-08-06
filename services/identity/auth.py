import os
import secrets
from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt
import redis.asyncio as redis
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from shared.auth_middleware import TokenData

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30
OTP_EXPIRE_MINUTES = 10

# Password context for any future password needs
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer security
security = HTTPBearer()

# OAuth configurations
OAUTH_CONFIGS = {
    "google": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
    },
    "apple": {
        "client_id": os.getenv("APPLE_CLIENT_ID"),
        "team_id": os.getenv("APPLE_TEAM_ID"),
        "key_id": os.getenv("APPLE_KEY_ID"),
        "private_key": os.getenv("APPLE_PRIVATE_KEY"),
        "redirect_uri": os.getenv("APPLE_REDIRECT_URI"),
        "token_url": "https://appleid.apple.com/auth/token",
    },
    "facebook": {
        "client_id": os.getenv("FACEBOOK_APP_ID"),
        "client_secret": os.getenv("FACEBOOK_APP_SECRET"),
        "redirect_uri": os.getenv("FACEBOOK_REDIRECT_URI"),
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "userinfo_url": "https://graph.facebook.com/me?fields=id,email,name,picture",
    },
}


class AuthService:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.http_client = httpx.AsyncClient()

    async def generate_otp(self) -> str:
        """Generate a 6-digit OTP"""
        return "".join([str(secrets.randbelow(10)) for _ in range(6)])

    async def store_otp(self, identifier: str, otp: str) -> None:
        """Store OTP in Redis with expiration"""
        key = f"otp:{identifier}"
        await self.redis.setex(key, OTP_EXPIRE_MINUTES * 60, otp)

    async def verify_otp(self, identifier: str, otp: str) -> bool:
        """Verify OTP from Redis"""
        key = f"otp:{identifier}"
        stored_otp = await self.redis.get(key)

        if not stored_otp:
            return False

        # Handle both string and bytes from Redis
        stored_otp_str = stored_otp.decode() if isinstance(stored_otp, bytes) else stored_otp

        if stored_otp_str == otp:
            await self.redis.delete(key)  # Delete after successful verification
            return True

        return False

    async def create_access_token(self, data: dict[str, Any]) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})

        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    async def create_refresh_token(self, data: dict[str, Any]) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})

        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        # Store refresh token in Redis for revocation capability
        await self.redis.setex(
            f"refresh_token:{data['user_id']}",
            REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            encoded_jwt,
        )

        return encoded_jwt

    async def decode_token(self, token: str) -> TokenData:
        """Decode and validate JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            # Filter payload to only include fields that TokenData expects
            filtered_payload = {
                k: v
                for k, v in payload.items()
                if k in {"user_id", "fairyname", "email", "is_builder", "is_admin", "exp", "type"}
            }
            return TokenData(**filtered_payload)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    async def get_oauth_token(self, provider: str, code: str) -> dict[str, Any]:
        """Exchange OAuth code for access token"""
        config = OAUTH_CONFIGS.get(provider)
        if not config:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

        if provider == "google":
            data = {
                "code": code,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            }
            response = await self.http_client.post(config["token_url"], data=data)

        elif provider == "facebook":
            params = {
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": config["redirect_uri"],
                "code": code,
            }
            response = await self.http_client.get(config["token_url"], params=params)

        elif provider == "apple":
            # Apple Sign In requires JWT client secret
            client_secret = self._create_apple_client_secret(config)
            data = {
                "code": code,
                "client_id": config["client_id"],
                "client_secret": client_secret,
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            }
            response = await self.http_client.post(
                config["token_url"],
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            error_text = response.text
            print(f"OAuth token error for {provider}: {response.status_code} - {error_text}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get OAuth token for {provider}: {error_text[:200]}",
            )

        return response.json()

    async def get_oauth_user_info(
        self, provider: str, access_token: str, id_token: str = None, user_data: dict = None
    ) -> dict[str, Any]:
        """Get user info from OAuth provider"""
        config = OAUTH_CONFIGS.get(provider)

        # Normalize user data across providers
        normalized = {"provider_id": None, "email": None, "name": None, "picture": None}

        if provider == "apple":
            # Apple provides user info in the ID token
            if not id_token:
                raise HTTPException(status_code=400, detail="Apple Sign In requires id_token")

            try:
                # Decode ID token without verification (Apple's public keys would be needed for full verification)
                # In production, you should verify the signature using Apple's public keys
                print("🔍 APPLE: Decoding ID token for user info extraction")
                decoded_token = jwt.decode(id_token, options={"verify_signature": False})
                print(f"📄 APPLE: Decoded token claims: {list(decoded_token.keys())}")

                normalized["provider_id"] = decoded_token.get("sub")
                normalized["email"] = decoded_token.get("email")

                print(f"👤 APPLE: Provider ID: {normalized['provider_id']}")
                print(f"📧 APPLE: Email: {normalized['email']}")

                # Apple provides name only in the first authorization request
                # Check user_data first, then fallback to token
                print(f"🔍 APPLE: Raw user_data received: {user_data}")
                print(f"🔍 APPLE: Decoded token data: {decoded_token}")

                if user_data and user_data.get("name"):
                    # User data from first sign-in (native apps)
                    print(f"📝 APPLE: Using name from user_data: {user_data['name']}")
                    name_data = user_data["name"]
                    if isinstance(name_data, dict):
                        # Format: {"firstName": "John", "lastName": "Doe"}
                        first_name = name_data.get("firstName", "")
                        last_name = name_data.get("lastName", "")
                        normalized["name"] = f"{first_name} {last_name}".strip()
                        normalized["first_name"] = first_name
                        normalized["last_name"] = last_name
                        print(f"📝 APPLE: Parsed name - First: '{first_name}', Last: '{last_name}'")
                    else:
                        normalized["name"] = str(name_data)
                else:
                    # Fallback to token (usually empty after first sign-in)
                    token_name = decoded_token.get("name")
                    print(f"📝 APPLE: Using name from token: {token_name}")
                    normalized["name"] = token_name

                # Check for DOB in various possible fields
                dob = None
                if user_data:
                    dob = (
                        user_data.get("birthdate")
                        or user_data.get("birthday")
                        or user_data.get("dob")
                    )
                if not dob and decoded_token:
                    dob = decoded_token.get("birthdate") or decoded_token.get("birthday")

                normalized["birthdate"] = dob
                print(f"🎂 APPLE: DOB found: {dob}")

                # Apple doesn't provide profile pictures
                normalized["picture"] = None

                print(f"✅ APPLE: Normalized user info: {normalized}")

            except jwt.InvalidTokenError as e:
                print(f"❌ APPLE: JWT decode error: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid Apple ID token: {str(e)}")

        else:
            # Google and Facebook use userinfo endpoints
            if not config or "userinfo_url" not in config:
                raise HTTPException(
                    status_code=400, detail=f"Cannot get user info for provider: {provider}"
                )

            headers = {"Authorization": f"Bearer {access_token}"}
            response = await self.http_client.get(config["userinfo_url"], headers=headers)

            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to get user info")

            user_data = response.json()

            if provider == "google":
                normalized["provider_id"] = user_data.get("id")
                normalized["email"] = user_data.get("email")
                normalized["name"] = user_data.get("name")
                normalized["picture"] = user_data.get("picture")

            elif provider == "facebook":
                normalized["provider_id"] = user_data.get("id")
                normalized["email"] = user_data.get("email")
                normalized["name"] = user_data.get("name")
                normalized["picture"] = user_data.get("picture", {}).get("data", {}).get("url")

        return normalized

    def _create_apple_client_secret(self, config: dict) -> str:
        """Create JWT client secret for Apple Sign In"""
        if not all(
            [
                config.get("team_id"),
                config.get("key_id"),
                config.get("private_key"),
                config.get("client_id"),
            ]
        ):
            raise HTTPException(
                status_code=500,
                detail="Missing Apple configuration: team_id, key_id, private_key, or client_id",
            )

        # Apple private key should be provided as a string with newlines
        private_key = config["private_key"].replace("\\n", "\n")

        # JWT header
        headers = {
            "alg": "ES256",
            "kid": config["key_id"],
        }

        # JWT payload
        now = datetime.utcnow()
        payload = {
            "iss": config["team_id"],
            "iat": int(now.timestamp()),
            "exp": int(
                (now + timedelta(minutes=5)).timestamp()
            ),  # Apple requires expiration within 6 months, we use 5 minutes
            "aud": "https://appleid.apple.com",
            "sub": config["client_id"],
        }

        # Create and return JWT
        try:
            return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to create Apple client secret: {str(e)}"
            )

    async def close(self):
        """Explicitly close the HTTP client"""
        await self.http_client.aclose()

    # Note: Removed __del__ to avoid RuntimeWarning with async cleanup
    # HTTP client will be cleaned up by garbage collection


# Dependency to get current user from JWT token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> TokenData:
    """Dependency to get current user from JWT token"""
    from shared.redis_client import get_redis

    redis_client = await get_redis()
    auth_service = AuthService(redis_client)
    token_data = await auth_service.decode_token(credentials.credentials)

    # Optionally check if token is revoked
    if token_data.user_id:
        is_revoked = await redis_client.get(f"revoked_token:{credentials.credentials}")
        if is_revoked:
            print(f"🔐 AUTH: Token revoked for user {token_data.user_id}", flush=True)
            raise HTTPException(status_code=401, detail="Token has been revoked")
    return token_data


# Builder role requirement removed - no longer supported


# Admin access dependency
async def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Require the current user to be an admin"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user
