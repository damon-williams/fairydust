from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from uuid import UUID
import httpx
import os
from pathlib import Path

# No more template dependencies needed!

from shared.database import get_db, Database
from shared.redis_client import get_redis
from auth import AdminAuth, get_current_admin_user, optional_admin_user

admin_router = APIRouter()

IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8001")

@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, admin_user: Optional[dict] = Depends(optional_admin_user)):
    if admin_user:
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fairydust Admin Login</title>
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
                                <h2 class="h4">Fairydust Admin</h2>
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
    """)

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
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fairydust Admin Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
            .stat-card {{ border-left: 4px solid; }}
            .stat-card-primary {{ border-left-color: #4e73df; }}
            .stat-card-success {{ border-left-color: #1cc88a; }}
            .stat-card-warning {{ border-left-color: #f6c23e; }}
            .stat-card-info {{ border-left-color: #36b9cc; }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> Fairydust Admin
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <h1>Dashboard</h1>
            
            <!-- Stats Cards -->
            <div class="row mb-4">
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-primary h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Users</div>
                                    <div class="h5 mb-0">{total_users["count"]}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-users fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-success h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Apps</div>
                                    <div class="h5 mb-0">{total_apps["count"]}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-mobile-alt fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-warning h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Pending Apps</div>
                                    <div class="h5 mb-0">{pending_apps["count"]}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-clock fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-info h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">DUST Issued</div>
                                    <div class="h5 mb-0 fairy-dust">{total_dust_issued["total"]:,}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-magic fa-2x text-warning"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Quick Actions -->
            <div class="row mb-4">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">Quick Actions</div>
                        <div class="card-body">
                            <a href="/admin/users" class="btn btn-primary me-2">Manage Users</a>
                            <a href="/admin/apps" class="btn btn-success">Manage Apps</a>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">System Status</div>
                        <div class="card-body">
                            <span class="badge bg-success">All Services Online</span>
                        </div>
                    </div>
                </div>
            </div>
            
            {f'<div class="alert alert-warning"><strong>Action Required:</strong> {pending_apps["count"]} apps pending approval. <a href="/admin/apps?status=pending">Review now</a></div>' if pending_apps["count"] > 0 else ''}
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """)

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
    
    users_html = ""
    for user in users:
        admin_badge = '<span class="badge bg-danger me-1">Admin</span>' if user["is_admin"] else ""
        builder_badge = '<span class="badge bg-info">Builder</span>' if user["is_builder"] else ""
        status_badge = '<span class="badge bg-success">Active</span>' if user["is_active"] else '<span class="badge bg-secondary">Inactive</span>'
        
        users_html += f"""
        <tr>
            <td><strong>{user["fairyname"]}</strong></td>
            <td>{user["email"] or user["phone"] or "N/A"}</td>
            <td><span class="fairy-dust">{user["dust_balance"]:,}</span></td>
            <td>{admin_badge}{builder_badge}</td>
            <td>{status_badge}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="grantDust('{user["id"]}', '{user["fairyname"]}')">
                    <i class="fas fa-magic"></i> Grant DUST
                </button>
            </td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Management - Fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> Fairydust Admin
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-users me-2"></i>User Management</h1>
                <a href="/admin/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Fairyname</th>
                                    <th>Contact</th>
                                    <th>DUST Balance</th>
                                    <th>Roles</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function grantDust(userId, userName) {{
                const amount = prompt(`Grant DUST to ${{userName}}:`, '100');
                const reason = prompt('Reason:', 'Admin grant');
                if (amount && reason) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/users/${{userId}}/grant-dust`;
                    
                    const amountInput = document.createElement('input');
                    amountInput.type = 'hidden';
                    amountInput.name = 'amount';
                    amountInput.value = amount;
                    
                    const reasonInput = document.createElement('input');
                    reasonInput.type = 'hidden';
                    reasonInput.name = 'reason';
                    reasonInput.value = reason;
                    
                    form.appendChild(amountInput);
                    form.appendChild(reasonInput);
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
        </script>
    </body>
    </html>
    """)

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
    
    apps_html = ""
    for app in apps:
        status_badge = ""
        if app["status"] == "approved":
            status_badge = '<span class="badge bg-success">Approved</span>'
        elif app["status"] == "pending":
            status_badge = '<span class="badge bg-warning">Pending</span>'
        elif app["status"] == "rejected":
            status_badge = '<span class="badge bg-danger">Rejected</span>'
        else:
            status_badge = f'<span class="badge bg-secondary">{app["status"]}</span>'
        
        approve_btn = f'<button class="btn btn-sm btn-success me-1" onclick="approveApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-check"></i></button>' if app["status"] == "pending" else ""
        reject_btn = f'<button class="btn btn-sm btn-danger" onclick="rejectApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-times"></i></button>' if app["status"] == "pending" else ""
        
        apps_html += f"""
        <tr>
            <td><strong>{app["name"]}</strong><br><small class="text-muted">{app["description"][:100]}...</small></td>
            <td>{app["builder_name"]}<br><small class="text-muted">{app["builder_email"]}</small></td>
            <td><span class="text-capitalize">{app["category"]}</span></td>
            <td>{status_badge}</td>
            <td>{approve_btn}{reject_btn}</td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>App Management - Fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> Fairydust Admin
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-mobile-alt me-2"></i>App Management</h1>
                <a href="/admin/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>App Details</th>
                                    <th>Builder</th>
                                    <th>Category</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {apps_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function approveApp(appId, appName) {{
                const notes = prompt(`Approve "${{appName}}"? Add notes (optional):`, '');
                if (notes !== null) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/apps/${{appId}}/approve`;
                    
                    const notesInput = document.createElement('input');
                    notesInput.type = 'hidden';
                    notesInput.name = 'admin_notes';
                    notesInput.value = notes;
                    
                    form.appendChild(notesInput);
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function rejectApp(appId, appName) {{
                const reason = prompt(`Reject "${{appName}}"? Please provide reason:`, '');
                if (reason) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/apps/${{appId}}/reject`;
                    
                    const reasonInput = document.createElement('input');
                    reasonInput.type = 'hidden';
                    reasonInput.name = 'admin_notes';
                    reasonInput.value = reason;
                    
                    form.appendChild(reasonInput);
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
        </script>
    </body>
    </html>
    """)

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