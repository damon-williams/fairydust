#!/usr/bin/env python3
"""
Generate a long-lived service JWT token for service-to-service authentication.

This token:
- Does not expire (no 'exp' claim)
- Has admin privileges
- Is meant for apps service → ledger service authentication
- Should be stored in SERVICE_JWT_TOKEN environment variable

Usage:
python scripts/generate_service_token.py --admin-user-id <uuid>
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

import jwt

# Same configuration as the identity service
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"

def generate_service_token(admin_user_id: str, expires_years: int = 10) -> str:
    """Generate a long-lived service JWT token for an admin user"""
    
    # Token payload - similar to regular user tokens but for service use
    payload = {
        "user_id": admin_user_id,
        "sub": admin_user_id,  # Standard JWT subject claim
        "fairyname": "SERVICE_TOKEN",
        "email": "service@fairydust.internal",
        "is_admin": True,
        "is_builder": True,
        "type": "service",
        "iat": datetime.utcnow().timestamp(),  # Issued at
    }
    
    # Add expiration (very long-lived but not infinite for security)
    if expires_years > 0:
        expire = datetime.utcnow() + timedelta(days=365 * expires_years)
        payload["exp"] = expire.timestamp()
    
    # Generate the token
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return token

def main():
    parser = argparse.ArgumentParser(description="Generate service JWT token")
    parser.add_argument("--admin-user-id", required=True, help="UUID of admin user")
    parser.add_argument("--expires-years", type=int, default=10, help="Token expiry in years (default: 10)")
    parser.add_argument("--no-expiry", action="store_true", help="Generate token with no expiration")
    
    args = parser.parse_args()
    
    # Validate UUID format
    try:
        from uuid import UUID
        UUID(args.admin_user_id)
    except ValueError:
        print(f"❌ Invalid UUID format: {args.admin_user_id}")
        sys.exit(1)
    
    expires_years = 0 if args.no_expiry else args.expires_years
    
    try:
        token = generate_service_token(args.admin_user_id, expires_years)
        
        print("🎯 Service JWT Token Generated Successfully!")
        print("=" * 60)
        print(f"Admin User ID: {args.admin_user_id}")
        if expires_years > 0:
            expire_date = datetime.utcnow() + timedelta(days=365 * expires_years)
            print(f"Expires: {expire_date.strftime('%Y-%m-%d %H:%M:%S')} UTC ({expires_years} years)")
        else:
            print("Expires: Never")
        print("=" * 60)
        print()
        print("🔑 TOKEN (save this to SERVICE_JWT_TOKEN environment variable):")
        print(token)
        print()
        print("📝 Railway Deployment Instructions:")
        print("1. Go to Railway dashboard")
        print("2. Select your fairydust-apps-staging (or production) service")
        print("3. Go to Variables tab")
        print("4. Add: SERVICE_JWT_TOKEN = <token above>")
        print("5. Redeploy the service")
        print()
        print("🧪 Test the token:")
        print(f"curl -H 'Authorization: Bearer {token}' https://your-ledger-url/health")
        
    except Exception as e:
        print(f"❌ Error generating token: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()