import os
import secrets
from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt
import redis.asyncio as redis
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models import TokenData
from passlib.context import CryptContext

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 525600
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
            return TokenData(**payload)
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
            # This is a simplified version - full implementation would generate JWT
            raise HTTPException(status_code=501, detail="Apple Sign In not yet implemented")

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get OAuth token")

        return response.json()

    async def get_oauth_user_info(self, provider: str, access_token: str) -> dict[str, Any]:
        """Get user info from OAuth provider"""
        config = OAUTH_CONFIGS.get(provider)
        if not config or "userinfo_url" not in config:
            raise HTTPException(
                status_code=400, detail=f"Cannot get user info for provider: {provider}"
            )

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.http_client.get(config["userinfo_url"], headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")

        user_data = response.json()

        # Normalize user data across providers
        normalized = {"provider_id": None, "email": None, "name": None, "picture": None}

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

    async def __del__(self):
        await self.http_client.aclose()


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
