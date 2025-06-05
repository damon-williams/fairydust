from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from uuid import UUID
import httpx
import os
from pathlib import Path

# Ensure jinja2 is available
try:
    import jinja2
    print(f"Jinja2 version: {jinja2.__version__}")
except ImportError as e:
    print(f"Jinja2 import error: {e}")
    print("Attempting to install jinja2 at runtime...")
    import subprocess
    import sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "jinja2==3.1.4", "markupsafe==2.1.3"])
        import jinja2
        print(f"Successfully installed jinja2 version: {jinja2.__version__}")
    except Exception as install_error:
        print(f"Failed to install jinja2: {install_error}")
        raise e

from fastapi.templating import Jinja2Templates

from shared.database import get_db, Database
from shared.redis_client import get_redis
from auth import AdminAuth, get_current_admin_user, optional_admin_user

admin_router = APIRouter()

# Initialize templates with debug info
template_dir = str(Path(__file__).parent / "templates")
print(f"Template directory: {template_dir}")
print(f"Template directory exists: {Path(template_dir).exists()}")

templates = Jinja2Templates(directory=template_dir)

IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8001")

@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, admin_user: Optional[dict] = Depends(optional_admin_user)):
    if admin_user:
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    
    return templates.TemplateResponse("login.html", {"request": request})

@admin_router.post("/login")
async def login(
    request: Request,
    identifier: str = Form(...),
    otp: str = Form(...),
    db: Database = Depends(get_db)
):
    # Verify user exists and is admin
    identifier_type = "email" if "@" in identifier else "phone"
    user = await db.fetch_one(
        f"SELECT * FROM users WHERE {identifier_type} = $1 AND is_admin = true AND is_active = true",
        identifier
    )
    
    if not user:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Admin access required"}
        )
    
    # Verify OTP via identity service
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{IDENTITY_SERVICE_URL}/auth/otp/verify",
                json={"identifier": identifier, "code": otp}
            )
            
            if response.status_code != 200:
                return templates.TemplateResponse(
                    "login.html",
                    {"request": request, "error": "Invalid OTP"}
                )
        except Exception:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Authentication service unavailable"}
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
        max_age=8 * 3600  # 8 hours
    )
    
    return response

@admin_router.post("/request-otp")
async def request_otp(identifier: str = Form(...)):
    """Request OTP for admin login"""
    async with httpx.AsyncClient() as client:
        try:
            identifier_type = "email" if "@" in identifier else "phone"
            response = await client.post(
                f"{IDENTITY_SERVICE_URL}/auth/otp/request",
                json={"identifier": identifier, "identifier_type": identifier_type}
            )
            
            if response.status_code == 200:
                return {"success": True, "message": f"OTP sent to {identifier_type}"}
            else:
                return {"success": False, "message": "Failed to send OTP"}
        except Exception:
            return {"success": False, "message": "Service unavailable"}

@admin_router.get("/logout")
async def logout(admin_user: dict = Depends(get_current_admin_user)):
    redis_client = await get_redis()
    auth = AdminAuth(redis_client)
    await auth.revoke_admin_session(admin_user["user_id"])
    
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response

@admin_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Get dashboard stats
    total_users = await db.fetch_one("SELECT COUNT(*) as count FROM users WHERE is_active = true")
    total_apps = await db.fetch_one("SELECT COUNT(*) as count FROM apps")
    pending_apps = await db.fetch_one("SELECT COUNT(*) as count FROM apps WHERE status = 'pending'")
    total_dust_issued = await db.fetch_one(
        "SELECT COALESCE(SUM(amount), 0) as total FROM dust_transactions WHERE type = 'grant'"
    )
    
    # Recent activity
    recent_users = await db.fetch_all(
        "SELECT fairyname, email, created_at FROM users WHERE is_active = true ORDER BY created_at DESC LIMIT 5"
    )
    
    recent_apps = await db.fetch_all(
        """
        SELECT a.name, a.status, a.created_at, u.fairyname as builder_name
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        ORDER BY a.created_at DESC
        LIMIT 5
        """
    )
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "admin_user": admin_user,
        "stats": {
            "total_users": total_users["count"],
            "total_apps": total_apps["count"],
            "pending_apps": pending_apps["count"],
            "total_dust_issued": total_dust_issued["total"]
        },
        "recent_users": recent_users,
        "recent_apps": recent_apps
    })

@admin_router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    page: int = 1,
    search: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    limit = 20
    offset = (page - 1) * limit
    
    # Build search query
    base_query = """
        SELECT id, fairyname, email, phone, is_builder, is_admin, 
               dust_balance, created_at, is_active
        FROM users
    """
    count_query = "SELECT COUNT(*) as total FROM users"
    
    params = []
    where_clause = ""
    
    if search:
        where_clause = " WHERE (fairyname ILIKE $1 OR email ILIKE $1 OR phone ILIKE $1)"
        params.append(f"%{search}%")
    
    users = await db.fetch_all(
        f"{base_query}{where_clause} ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}",
        *params
    )
    
    total_count = await db.fetch_one(f"{count_query}{where_clause}", *params)
    total_pages = (total_count["total"] + limit - 1) // limit
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "admin_user": admin_user,
        "users": users,
        "current_page": page,
        "total_pages": total_pages,
        "search": search or ""
    })

@admin_router.post("/users/{user_id}/grant-dust")
async def grant_dust(
    user_id: str,
    amount: int = Form(...),
    reason: str = Form(...),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    # Verify user exists
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create transaction and update balance
    async with db.transaction() as conn:
        # Insert transaction
        await conn.execute(
            """
            INSERT INTO dust_transactions (user_id, amount, type, description)
            VALUES ($1, $2, 'admin_grant', $3)
            """,
            user_id, amount, f"Admin grant: {reason}"
        )
        
        # Update user balance
        await conn.execute(
            "UPDATE users SET dust_balance = dust_balance + $1 WHERE id = $2",
            amount, user_id
        )
    
    return RedirectResponse(url=f"/admin/users?granted={amount}", status_code=302)

@admin_router.post("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Verify user exists
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't allow removing own admin status
    if user_id == admin_user["user_id"] and user["is_admin"]:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin privileges")
    
    # Toggle admin status
    new_admin_status = not user["is_admin"]
    await db.execute(
        "UPDATE users SET is_admin = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
        new_admin_status, user_id
    )
    
    return RedirectResponse(url="/admin/users", status_code=302)

@admin_router.get("/apps", response_class=HTMLResponse)
async def apps_list(
    request: Request,
    status_filter: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Build query with optional status filter
    base_query = """
        SELECT a.*, u.fairyname as builder_name, u.email as builder_email
        FROM apps a
        JOIN users u ON a.builder_id = u.id
    """
    
    params = []
    where_clause = ""
    
    if status_filter and status_filter != "all":
        where_clause = " WHERE a.status = $1"
        params.append(status_filter)
    
    apps = await db.fetch_all(
        f"{base_query}{where_clause} ORDER BY a.created_at DESC",
        *params
    )
    
    return templates.TemplateResponse("apps.html", {
        "request": request,
        "admin_user": admin_user,
        "apps": apps,
        "status_filter": status_filter or "all"
    })

@admin_router.post("/apps/{app_id}/approve")
async def approve_app(
    app_id: str,
    admin_notes: str = Form(""),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    await db.execute(
        """
        UPDATE apps 
        SET status = 'approved', is_active = true, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Approved by {admin_user['fairyname']}: {admin_notes}" if admin_notes else f"Approved by {admin_user['fairyname']}",
        app_id
    )
    
    return RedirectResponse(url="/admin/apps", status_code=302)

@admin_router.post("/apps/{app_id}/reject")
async def reject_app(
    app_id: str,
    admin_notes: str = Form(...),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    await db.execute(
        """
        UPDATE apps 
        SET status = 'rejected', is_active = false, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Rejected by {admin_user['fairyname']}: {admin_notes}",
        app_id
    )
    
    return RedirectResponse(url="/admin/apps", status_code=302)