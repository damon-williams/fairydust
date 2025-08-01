import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
import redis.asyncio as redis
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

# JWT is working fine now
from shared.database import Database, get_db
from shared.redis_client import get_redis

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ADMIN_SESSION_EXPIRE_HOURS = 8

security = HTTPBearer(auto_error=False)


class AdminAuth:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def create_admin_session(self, user_id: str, fairyname: str) -> str:
        """Create admin session token"""
        payload = {
            "user_id": user_id,
            "fairyname": fairyname,
            "exp": datetime.utcnow() + timedelta(hours=ADMIN_SESSION_EXPIRE_HOURS),
            "type": "admin_session",
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        # Store in Redis for revocation capability
        await self.redis.setex(f"admin_session:{user_id}", ADMIN_SESSION_EXPIRE_HOURS * 3600, token)

        return token

    async def verify_admin_session(self, token: str) -> Optional[dict]:
        """Verify admin session token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

            # Check if session exists in Redis
            stored_token = await self.redis.get(f"admin_session:{payload['user_id']}")
            if not stored_token:
                return None

            # Handle both bytes and string from Redis
            stored_token_str = (
                stored_token.decode() if isinstance(stored_token, bytes) else stored_token
            )
            if stored_token_str != token:
                return None

            return payload
        except jwt.ExpiredSignatureError:
            print("JWT token expired")
            return None
        except jwt.PyJWTError:
            print("JWT verification failed")
            return None
        except Exception as e:
            print(f"Unexpected JWT error: {e}")
            return None

    async def revoke_admin_session(self, user_id: str):
        """Revoke admin session"""
        await self.redis.delete(f"admin_session:{user_id}")


async def get_current_admin_user(
    request: Request, admin_session: Optional[str] = Cookie(None), db: Database = Depends(get_db)
) -> dict:
    """Get current admin user from session cookie"""
    if not admin_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    redis_client = await get_redis()
    auth = AdminAuth(redis_client)

    session_data = await auth.verify_admin_session(admin_session)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Verify user is still admin
    from uuid import UUID

    try:
        user_id = (
            UUID(session_data["user_id"])
            if isinstance(session_data["user_id"], str)
            else session_data["user_id"]
        )
        user = await db.fetch_one(
            "SELECT id, fairyname, email, is_admin, is_active FROM users WHERE id = $1 AND is_admin = true AND is_active = true",
            user_id,
        )
    except Exception as e:
        print(f"Database error in admin auth: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

    if not user:
        raise HTTPException(status_code=403, detail="Admin access revoked")

    return {
        "user_id": session_data["user_id"],
        "fairyname": session_data["fairyname"],
        "user": dict(user),
    }


async def optional_admin_user(
    request: Request, admin_session: Optional[str] = Cookie(None), db: Database = Depends(get_db)
) -> Optional[dict]:
    """Get current admin user if authenticated, otherwise None"""
    try:
        return await get_current_admin_user(request, admin_session, db)
    except Exception:
        # Catch all exceptions (HTTPException, database errors, etc.)
        return None
