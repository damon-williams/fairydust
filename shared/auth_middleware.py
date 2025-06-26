# shared/auth_middleware.py
import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"

security = HTTPBearer()


class TokenData(BaseModel):
    user_id: str
    fairyname: str
    email: Optional[str] = None
    is_builder: bool = False
    is_admin: bool = False


def verify_token(token: str) -> TokenData:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Try both 'sub' (standard) and 'user_id' (your token format)
        user_id = payload.get("sub") or payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing user ID"
            )

        return TokenData(
            user_id=user_id,
            fairyname=payload.get("fairyname", ""),
            email=payload.get("email"),
            is_builder=payload.get("is_builder", False),
            is_admin=payload.get("is_admin", False),
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenData:
    """FastAPI dependency to get current user from JWT token"""
    return verify_token(credentials.credentials)


async def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """FastAPI dependency that requires admin privileges"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[TokenData]:
    """FastAPI dependency to get current user, but don't require authentication"""
    if credentials is None:
        return None

    try:
        return verify_token(credentials.credentials)
    except HTTPException:
        return None
