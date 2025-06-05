import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Request, Depends, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as redis

# Debug JWT module
print(f"JWT module: {jwt}")
print(f"JWT attributes: {dir(jwt)}")
try:
    print(f"JWTError available: {hasattr(jwt, 'JWTError')}")
    if hasattr(jwt, 'JWTError'):
        print(f"JWTError: {jwt.JWTError}")
except Exception as e:
    print(f"Error checking JWTError: {e}")

from shared.database import get_db, Database
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
            "type": "admin_session"
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        
        # Store in Redis for revocation capability
        await self.redis.setex(
            f"admin_session:{user_id}",
            ADMIN_SESSION_EXPIRE_HOURS * 3600,
            token
        )
        
        return token
    
    async def verify_admin_session(self, token: str) -> Optional[dict]:
        """Verify admin session token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check if session exists in Redis
            stored_token = await self.redis.get(f"admin_session:{payload['user_id']}")
            if not stored_token or stored_token.decode() != token:
                return None
            
            return payload
        except Exception as e:
            # Handle any JWT-related errors
            print(f"JWT verification error: {e}")
            return None
    
    async def revoke_admin_session(self, user_id: str):
        """Revoke admin session"""
        await self.redis.delete(f"admin_session:{user_id}")

async def get_current_admin_user(
    request: Request,
    admin_session: Optional[str] = Cookie(None),
    db: Database = Depends(get_db)
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
    user = await db.fetch_one(
        "SELECT * FROM users WHERE id = $1 AND is_admin = true AND is_active = true",
        session_data["user_id"]
    )
    
    if not user:
        raise HTTPException(status_code=403, detail="Admin access revoked")
    
    return {
        "user_id": session_data["user_id"],
        "fairyname": session_data["fairyname"],
        "user": dict(user)
    }

async def optional_admin_user(
    request: Request,
    admin_session: Optional[str] = Cookie(None),
    db: Database = Depends(get_db)
) -> Optional[dict]:
    """Get current admin user if authenticated, otherwise None"""
    try:
        return await get_current_admin_user(request, admin_session, db)
    except HTTPException:
        return None