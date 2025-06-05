import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Request, Depends, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as redis

from shared.database import get_db, Database
from shared.redis_client import get_redis

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
BUILDER_SESSION_EXPIRE_HOURS = 8

security = HTTPBearer(auto_error=False)

class BuilderAuth:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def create_builder_session(self, user_id: str, fairyname: str) -> str:
        """Create builder session token"""
        payload = {
            "user_id": user_id,
            "fairyname": fairyname,
            "exp": datetime.utcnow() + timedelta(hours=BUILDER_SESSION_EXPIRE_HOURS),
            "type": "builder_session"
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        
        # Store in Redis for revocation capability
        await self.redis.setex(
            f"builder_session:{user_id}",
            BUILDER_SESSION_EXPIRE_HOURS * 3600,
            token
        )
        
        return token
    
    async def verify_builder_session(self, token: str) -> Optional[dict]:
        """Verify builder session token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check if session exists in Redis
            stored_token = await self.redis.get(f"builder_session:{payload['user_id']}")
            if not stored_token:
                return None
            
            # Handle both bytes and string from Redis
            stored_token_str = stored_token.decode() if isinstance(stored_token, bytes) else stored_token
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
    
    async def revoke_builder_session(self, user_id: str):
        """Revoke builder session"""
        await self.redis.delete(f"builder_session:{user_id}")

async def get_current_builder_user(
    request: Request,
    builder_session: Optional[str] = Cookie(None),
    db: Database = Depends(get_db)
) -> dict:
    """Get current builder user from session cookie"""
    if not builder_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    redis_client = await get_redis()
    auth = BuilderAuth(redis_client)
    
    session_data = await auth.verify_builder_session(builder_session)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # Verify user exists and is a builder
    user = await db.fetch_one(
        "SELECT * FROM users WHERE id = $1 AND is_builder = true AND is_active = true",
        session_data["user_id"]
    )
    
    if not user:
        raise HTTPException(status_code=403, detail="Builder access required")
    
    return {
        "user_id": session_data["user_id"],
        "fairyname": session_data["fairyname"],
        "user": dict(user)
    }

async def optional_builder_user(
    request: Request,
    builder_session: Optional[str] = Cookie(None),
    db: Database = Depends(get_db)
) -> Optional[dict]:
    """Get current builder user if authenticated, otherwise None"""
    try:
        return await get_current_builder_user(request, builder_session, db)
    except HTTPException:
        return None