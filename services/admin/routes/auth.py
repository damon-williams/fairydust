import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
import jwt
from auth import AdminAuth, get_current_admin_user, optional_admin_user
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from shared.database import Database, get_db
from shared.redis_client import get_redis

auth_router = APIRouter()

IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8001")

# JWT Configuration - same as identity service
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, admin_user: Optional[dict] = Depends(optional_admin_user)):
    if admin_user:
        return RedirectResponse(url="/admin/dashboard", status_code=302)

    return HTMLResponse(
        """
    <!DOCTYPE html>
    <html>
    <head>
        <title>fairydust Admin Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
            .login-card { border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
            .fairy-dust { color: #ffd700; text-shadow: 0 0 10px rgba(255,215,0,0.5); }
        </style>
    </head>
    <body class="d-flex align-items-center">
        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-6 col-lg-4">
                    <div class="card login-card">
                        <div class="card-body p-5">
                            <div class="text-center mb-4">
                                <h1><i class="fas fa-magic fairy-dust fs-1"></i></h1>
                                <h2 class="h4">fairydust</h2>
                                <p class="text-muted">Admin Portal</p>
                            </div>

                            <form method="post" action="/admin/login" id="loginForm">
                                <div class="mb-3">
                                    <label class="form-label">Email or Phone</label>
                                    <input type="text" class="form-control" name="identifier" required>
                                </div>

                                <div class="mb-3" id="otpSection" style="display: none;">
                                    <label class="form-label">OTP Code</label>
                                    <input type="text" class="form-control" name="otp" maxlength="6">
                                </div>

                                <div class="d-grid gap-2">
                                    <button type="button" class="btn btn-outline-primary" id="requestOtpBtn" onclick="requestOTP()">
                                        Send OTP
                                    </button>
                                    <button type="submit" class="btn btn-primary" id="loginBtn" style="display: none;">
                                        Login
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/js/all.min.js"></script>
        <script>
            async function requestOTP() {
                const identifier = document.querySelector('input[name="identifier"]').value;
                if (!identifier) { alert('Please enter email or phone'); return; }

                const btn = document.getElementById('requestOtpBtn');
                btn.innerHTML = 'Sending...'; btn.disabled = true;

                try {
                    const formData = new FormData();
                    formData.append('identifier', identifier);
                    const response = await fetch('/admin/request-otp', { method: 'POST', body: formData });
                    const result = await response.json();

                    if (result.success) {
                        document.getElementById('otpSection').style.display = 'block';
                        document.getElementById('loginBtn').style.display = 'block';
                        btn.style.display = 'none';
                    } else {
                        alert(result.message || 'Failed to send OTP');
                    }
                } catch (error) {
                    alert('Network error');
                } finally {
                    btn.innerHTML = 'Send OTP'; btn.disabled = false;
                }
            }
        </script>
    </body>
    </html>
    """
    )


@auth_router.post("/login")
async def login(
    request: Request,
    identifier: str = Form(...),
    otp: str = Form(...),
    db: Database = Depends(get_db),
):
    # Verify user exists and is admin
    identifier_type = "email" if "@" in identifier else "phone"
    user = await db.fetch_one(
        f"SELECT * FROM users WHERE {identifier_type} = $1 AND is_admin = true AND is_active = true",
        identifier,
    )

    if not user:
        return HTMLResponse(
            """
            <script>
                alert('Admin access required. Please contact support.');
                window.location.href = '/admin/login';
            </script>
        """
        )

    # Verify OTP via identity service
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{IDENTITY_SERVICE_URL}/auth/otp/verify",
                json={"identifier": identifier, "code": otp},
            )

            if response.status_code != 200:
                return HTMLResponse(
                    """
                    <script>
                        alert('Invalid OTP');
                        window.location.href = '/admin/login';
                    </script>
                """
                )
        except Exception:
            return HTMLResponse(
                """
                <script>
                    alert('Authentication service unavailable');
                    window.location.href = '/admin/login';
                </script>
            """
            )

    # Create admin session
    redis_client = await get_redis()
    auth = AdminAuth(redis_client)
    session_token = await auth.create_admin_session(str(user["id"]), user["fairyname"])

    # Set session cookie and redirect
    response = RedirectResponse(url="/admin/dashboard", status_code=302)
    response.set_cookie(
        key="admin_session",
        value=session_token,
        httponly=True,
        secure=True if os.getenv("ENVIRONMENT") == "production" else False,
        samesite="lax",
        max_age=8 * 3600,  # 8 hours
    )

    return response


@auth_router.post("/request-otp")
async def request_otp(identifier: str = Form(...)):
    """Request OTP for admin login"""
    async with httpx.AsyncClient() as client:
        try:
            identifier_type = "email" if "@" in identifier else "phone"
            response = await client.post(
                f"{IDENTITY_SERVICE_URL}/auth/otp/request",
                json={"identifier": identifier, "identifier_type": identifier_type},
            )

            if response.status_code == 200:
                return {"success": True, "message": f"OTP sent to {identifier_type}"}
            else:
                return {"success": False, "message": "Failed to send OTP"}
        except Exception:
            return {"success": False, "message": "Service unavailable"}


@auth_router.get("/me")
async def get_current_admin_user_info(admin_user: dict = Depends(get_current_admin_user)):
    """Get current admin user information"""
    user_data = admin_user.get("user", {})
    return {
        "id": admin_user["user_id"],
        "fairyname": admin_user["fairyname"],
        "email": user_data.get("email"),
        "is_admin": True,
    }


@auth_router.get("/logout")
async def logout(admin_user: dict = Depends(get_current_admin_user)):
    redis_client = await get_redis()
    auth = AdminAuth(redis_client)
    await auth.revoke_admin_session(admin_user["user_id"])

    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response


@auth_router.post("/service-token/generate")
async def generate_service_token(admin_user: dict = Depends(get_current_admin_user)):
    """Generate a long-lived service JWT token for service-to-service authentication"""
    
    # Use the current admin user's ID for the service token
    admin_user_id = admin_user["user_id"]
    
    # Token payload - long-lived service token with admin privileges
    payload = {
        "user_id": admin_user_id,
        "sub": admin_user_id,  # Standard JWT subject claim
        "fairyname": f"SERVICE_TOKEN_{admin_user['fairyname']}",
        "email": admin_user.get("email", "service@fairydust.internal"),
        "is_admin": True,
        "is_builder": True,
        "type": "service",
        "iat": datetime.utcnow().timestamp(),  # Issued at
        "generated_by": admin_user_id,
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    # Set expiration to 10 years (very long-lived but not infinite)
    expires_years = 10
    expire_date = datetime.utcnow() + timedelta(days=365 * expires_years)
    payload["exp"] = expire_date.timestamp()
    
    # Generate the token
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    return {
        "token": token,
        "expires": expire_date.isoformat(),
        "generated_for": admin_user["fairyname"],
        "usage": "Set this as SERVICE_JWT_TOKEN environment variable in apps service"
    }
