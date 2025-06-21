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
        return HTMLResponse("""
            <script>
                alert('Admin access required. Please contact support.');
                window.location.href = '/admin/login';
            </script>
        """)
    
    # Verify OTP via identity service
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{IDENTITY_SERVICE_URL}/auth/otp/verify",
                json={"identifier": identifier, "code": otp}
            )
            
            if response.status_code != 200:
                return HTMLResponse("""
                    <script>
                        alert('Invalid OTP');
                        window.location.href = '/admin/login';
                    </script>
                """)
        except Exception:
            return HTMLResponse("""
                <script>
                    alert('Authentication service unavailable');
                    window.location.href = '/admin/login';
                </script>
            """)
    
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
        <title>fairydust Admin Dashboard</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <h1>Admin Dashboard</h1>
            
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
                            <a href="/admin/apps" class="btn btn-success me-2">Manage Apps</a>
                            <a href="/admin/questions" class="btn btn-info me-2">Manage Questions</a>
                            <a href="/admin/llm" class="btn btn-warning">LLM Analytics</a>
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
                <button class="btn btn-sm btn-primary me-1" onclick="grantDust('{user["id"]}', '{user["fairyname"]}')">
                    <i class="fas fa-magic"></i>
                </button>
                <button class="btn btn-sm {'btn-info' if user["is_builder"] else 'btn-outline-info'} me-1" 
                        onclick="toggleBuilder('{user["id"]}', '{user["fairyname"]}', {str(user["is_builder"]).lower()})"
                        title="{'Remove' if user["is_builder"] else 'Grant'} Builder Access">
                    <i class="fas fa-hammer"></i>
                </button>
                <button class="btn btn-sm {'btn-danger' if user["is_admin"] else 'btn-outline-danger'}" 
                        onclick="toggleAdmin('{user["id"]}', '{user["fairyname"]}', {str(user["is_admin"]).lower()})"
                        title="{'Remove' if user["is_admin"] else 'Grant'} Admin Access"
                        {'disabled' if user["id"] == admin_user["user_id"] and user["is_admin"] else ''}>
                    <i class="fas fa-user-shield"></i>
                </button>
            </td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Management - fairydust Admin</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
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
                <a href="/admin/dashboard" class="btn btn-secondary">← Back to Admin Dashboard</a>
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
            
            function toggleBuilder(userId, userName, isCurrentlyBuilder) {{
                const action = isCurrentlyBuilder ? 'remove' : 'grant';
                if (confirm(`${{action === 'grant' ? 'Grant' : 'Remove'}} builder access for ${{userName}}?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/users/${{userId}}/toggle-builder`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function toggleAdmin(userId, userName, isCurrentlyAdmin) {{
                const action = isCurrentlyAdmin ? 'remove' : 'grant';
                if (confirm(`${{action === 'grant' ? 'Grant' : 'Remove'}} admin access for ${{userName}}?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/users/${{userId}}/toggle-admin`;
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

@admin_router.post("/users/{user_id}/toggle-builder")
async def toggle_builder(
    user_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Verify user exists
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Toggle builder status
    new_builder_status = not user["is_builder"]
    await db.execute(
        "UPDATE users SET is_builder = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
        new_builder_status, user_id
    )
    
    return RedirectResponse(url="/admin/users", status_code=302)

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
        elif app["status"] == "suspended":
            status_badge = '<span class="badge bg-dark">Suspended</span>'
        else:
            status_badge = f'<span class="badge bg-secondary">{app["status"]}</span>'
        
        # Action buttons based on current status
        approve_btn = f'<button class="btn btn-sm btn-success me-1" onclick="approveApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-check"></i></button>' if app["status"] == "pending" else ""
        reject_btn = f'<button class="btn btn-sm btn-danger me-1" onclick="rejectApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-times"></i></button>' if app["status"] == "pending" else ""
        suspend_btn = f'<button class="btn btn-sm btn-warning me-1" onclick="suspendApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-pause"></i></button>' if app["status"] == "approved" else ""
        reactivate_btn = f'<button class="btn btn-sm btn-info me-1" onclick="reactivateApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-play"></i></button>' if app["status"] == "suspended" else ""
        
        apps_html += f"""
        <tr>
            <td><strong>{app["name"]}</strong><br><small class="text-muted">{app["description"][:100]}...</small></td>
            <td>{app["builder_name"]}<br><small class="text-muted">{app["builder_email"]}</small></td>
            <td><span class="text-capitalize">{app["category"]}</span></td>
            <td>{status_badge}</td>
            <td>{approve_btn}{reject_btn}{suspend_btn}{reactivate_btn}</td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>App Management - fairydust Admin</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
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
                <a href="/admin/dashboard" class="btn btn-secondary">← Back to Admin Dashboard</a>
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
            
            function suspendApp(appId, appName) {{
                const reason = prompt(`Suspend "${{appName}}"? Please provide reason:`, '');
                if (reason) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/apps/${{appId}}/suspend`;
                    
                    const reasonInput = document.createElement('input');
                    reasonInput.type = 'hidden';
                    reasonInput.name = 'admin_notes';
                    reasonInput.value = reason;
                    
                    form.appendChild(reasonInput);
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function reactivateApp(appId, appName) {{
                if (confirm(`Reactivate "${{appName}}"?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/apps/${{appId}}/reactivate`;
                    
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

@admin_router.post("/apps/{app_id}/suspend")
async def suspend_app(
    app_id: str,
    admin_notes: str = Form(...),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    await db.execute(
        """
        UPDATE apps 
        SET status = 'suspended', is_active = false, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Suspended by {admin_user['fairyname']}: {admin_notes}",
        app_id
    )
    
    return RedirectResponse(url="/admin/apps", status_code=302)

@admin_router.post("/apps/{app_id}/reactivate")
async def reactivate_app(
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    await db.execute(
        """
        UPDATE apps 
        SET status = 'approved', is_active = true, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Reactivated by {admin_user['fairyname']}",
        app_id
    )
    
    return RedirectResponse(url="/admin/apps", status_code=302)

# Question Management Routes
@admin_router.get("/questions", response_class=HTMLResponse)
async def questions_list(
    request: Request,
    category: Optional[str] = None,
    status: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Build query with optional filters
    base_query = """
        SELECT q.*, 
               COUNT(r.id) as response_count
        FROM profiling_questions q
        LEFT JOIN user_question_responses r ON q.id = r.question_id
    """
    
    params = []
    where_conditions = []
    
    if category and category != "all":
        where_conditions.append("q.category = $" + str(len(params) + 1))
        params.append(category)
    
    if status == "active":
        where_conditions.append("q.is_active = true")
    elif status == "inactive":
        where_conditions.append("q.is_active = false")
    
    where_clause = ""
    if where_conditions:
        where_clause = " WHERE " + " AND ".join(where_conditions)
    
    questions = await db.fetch_all(
        f"{base_query}{where_clause} GROUP BY q.id ORDER BY q.priority DESC, q.category, q.id",
        *params
    )
    
    # Get categories for filter dropdown
    categories = await db.fetch_all("SELECT DISTINCT category FROM profiling_questions ORDER BY category")
    
    # Build filter dropdown options
    category_options = '<option value="all">All Categories</option>'
    for cat in categories:
        selected = 'selected' if category == cat["category"] else ''
        category_options += f'<option value="{cat["category"]}" {selected}>{cat["category"].title()}</option>'
    
    # Build questions table
    questions_html = ""
    for q in questions:
        status_badge = '<span class="badge bg-success">Active</span>' if q["is_active"] else '<span class="badge bg-secondary">Inactive</span>'
        type_badge = f'<span class="badge bg-light text-dark">{q["question_type"]}</span>'
        
        # Truncate long question text
        question_text = q["question_text"]
        if len(question_text) > 80:
            question_text = question_text[:80] + "..."
        
        questions_html += f"""
        <tr>
            <td>
                <strong>{question_text}</strong><br>
                <small class="text-muted">ID: {q["id"]}</small>
            </td>
            <td><span class="text-capitalize">{q["category"]}</span></td>
            <td>{type_badge}</td>
            <td><span class="badge bg-primary">{q["priority"]}</span></td>
            <td><span class="badge bg-info">{q["response_count"]}</span></td>
            <td>{status_badge}</td>
            <td>
                <button class="btn btn-sm btn-primary me-1" onclick="editQuestion('{q["id"]}')" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm {'btn-success' if q["is_active"] else 'btn-warning'} me-1" 
                        onclick="toggleQuestion('{q["id"]}', '{q["question_text"][:30]}...', {str(q["is_active"]).lower()})"
                        title="{'Disable' if q["is_active"] else 'Enable'}">
                    <i class="fas fa-{'toggle-on' if q["is_active"] else 'toggle-off'}"></i>
                </button>
                <button class="btn btn-sm btn-secondary me-1" 
                        onclick="duplicateQuestion('{q["id"]}', '{q["question_text"][:30]}...')"
                        title="Duplicate">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="btn btn-sm btn-danger" 
                        onclick="deleteQuestion('{q["id"]}', '{q["question_text"][:30]}...')"
                        title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Question Management - fairydust Admin</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-question-circle me-2"></i>Question Management</h1>
                <div>
                    <a href="/admin/questions/new" class="btn btn-success me-2">
                        <i class="fas fa-plus"></i> Add New Question
                    </a>
                    <a href="/admin/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
                </div>
            </div>
            
            <!-- Filters -->
            <div class="card mb-4">
                <div class="card-body">
                    <form method="get" class="row g-3">
                        <div class="col-md-4">
                            <label class="form-label">Category</label>
                            <select name="category" class="form-select" onchange="this.form.submit()">
                                {category_options}
                            </select>
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">Status</label>
                            <select name="status" class="form-select" onchange="this.form.submit()">
                                <option value="">All Status</option>
                                <option value="active" {'selected' if status == 'active' else ''}>Active</option>
                                <option value="inactive" {'selected' if status == 'inactive' else ''}>Inactive</option>
                            </select>
                        </div>
                        <div class="col-md-4 d-flex align-items-end">
                            <button type="submit" class="btn btn-primary me-2">Filter</button>
                            <a href="/admin/questions" class="btn btn-outline-secondary">Clear</a>
                        </div>
                    </form>
                </div>
            </div>
            
            <!-- Questions Table -->
            <div class="card">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Question</th>
                                    <th>Category</th>
                                    <th>Type</th>
                                    <th>Priority</th>
                                    <th>Responses</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {questions_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function editQuestion(questionId) {{
                window.location.href = `/admin/questions/${{questionId}}/edit`;
            }}
            
            function toggleQuestion(questionId, questionText, isCurrentlyActive) {{
                const action = isCurrentlyActive ? 'disable' : 'enable';
                if (confirm(`${{action === 'enable' ? 'Enable' : 'Disable'}} question "${{questionText}}"?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/questions/${{questionId}}/toggle`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function duplicateQuestion(questionId, questionText) {{
                if (confirm(`Duplicate question "${{questionText}}"?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/questions/${{questionId}}/duplicate`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function deleteQuestion(questionId, questionText) {{
                if (confirm(`DELETE question "${{questionText}}"? This cannot be undone!`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/questions/${{questionId}}/delete`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
        </script>
    </body>
    </html>
    """)

@admin_router.get("/questions/new", response_class=HTMLResponse)
async def new_question_form(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user)
):
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add New Question - fairydust Admin</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-plus-circle me-2"></i>Add New Question</h1>
                <a href="/admin/questions" class="btn btn-secondary">← Back to Questions</a>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <form method="post" action="/admin/questions">
                        <div class="row">
                            <div class="col-md-8">
                                <div class="mb-3">
                                    <label class="form-label">Question ID</label>
                                    <input type="text" class="form-control" name="id" required 
                                           placeholder="e.g., cooking_experience" pattern="[a-z_]+" 
                                           title="Lowercase letters and underscores only">
                                    <div class="form-text">Unique identifier (lowercase, underscores only)</div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Question Text</label>
                                    <textarea class="form-control" name="question_text" rows="3" required 
                                              placeholder="How would you describe your cooking experience?"></textarea>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Category</label>
                                            <input type="text" class="form-control" name="category" required 
                                                   placeholder="e.g., cooking, personality, goals">
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Question Type</label>
                                            <select class="form-select" name="question_type" required onchange="updateOptionsSection()">
                                                <option value="">Select Type</option>
                                                <option value="single_choice">Single Choice</option>
                                                <option value="multi_select">Multi Select</option>
                                                <option value="scale">Scale (1-5)</option>
                                                <option value="text">Text Input</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Profile Field</label>
                                            <input type="text" class="form-control" name="profile_field" required 
                                                   placeholder="cooking_experience">
                                            <div class="form-text">Field name to store in user profile</div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Priority</label>
                                            <input type="number" class="form-control" name="priority" value="5" min="1" max="10" required>
                                            <div class="form-text">1-10 (higher = shown earlier)</div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">App Context</label>
                                    <input type="text" class="form-control" name="app_context" 
                                           placeholder='["fairydust-recipe", "fairydust-inspire"]' 
                                           value='["fairydust-recipe"]'>
                                    <div class="form-text">JSON array of apps that should show this question</div>
                                </div>
                                
                                <div id="optionsSection" style="display: none;">
                                    <div class="mb-3">
                                        <label class="form-label">Options (JSON)</label>
                                        <textarea class="form-control" name="options" rows="6" 
                                                  placeholder='[{"id": "beginner", "label": "Beginner"}, {"id": "intermediate", "label": "Intermediate"}]'></textarea>
                                        <div class="form-text">JSON array of options for choice questions</div>
                                    </div>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" name="is_active" checked>
                                    <label class="form-check-label">
                                        Active (show to users)
                                    </label>
                                </div>
                            </div>
                            
                            <div class="col-md-4">
                                <div class="card bg-light">
                                    <div class="card-header">
                                        <h6 class="mb-0">Preview</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="questionPreview">
                                            <em>Fill out the form to see preview</em>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <hr>
                        <div class="d-flex justify-content-end">
                            <a href="/admin/questions" class="btn btn-outline-secondary me-2">Cancel</a>
                            <button type="submit" class="btn btn-success">
                                <i class="fas fa-save"></i> Create Question
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function updateOptionsSection() {{
                const questionType = document.querySelector('[name="question_type"]').value;
                const optionsSection = document.getElementById('optionsSection');
                const optionsTextarea = document.querySelector('[name="options"]');
                
                if (questionType === 'single_choice' || questionType === 'multi_select') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                    
                    if (questionType === 'single_choice') {{
                        optionsTextarea.placeholder = '[{{"id": "beginner", "label": "Beginner"}}, {{"id": "intermediate", "label": "Intermediate"}}, {{"id": "advanced", "label": "Advanced"}}]';
                    }} else {{
                        optionsTextarea.placeholder = '[{{"id": "option1", "label": "Option 1"}}, {{"id": "option2", "label": "Option 2"}}, {{"id": "option3", "label": "Option 3"}}]';
                    }}
                }} else if (questionType === 'scale') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                    optionsTextarea.placeholder = '{{"min": 1, "max": 5, "labels": {{"1": "Not at all", "3": "Somewhat", "5": "Very much"}}}}';
                }} else {{
                    optionsSection.style.display = 'none';
                    optionsTextarea.required = false;
                    optionsTextarea.value = '';
                }}
                
                updatePreview();
            }}
            
            function updatePreview() {{
                const questionText = document.querySelector('[name="question_text"]').value;
                const questionType = document.querySelector('[name="question_type"]').value;
                const preview = document.getElementById('questionPreview');
                
                if (questionText && questionType) {{
                    let previewHtml = `<strong>${{questionText}}</strong><br><br>`;
                    
                    if (questionType === 'single_choice') {{
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="radio" disabled><label class="form-check-label">Option 1</label></div>';
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="radio" disabled><label class="form-check-label">Option 2</label></div>';
                    }} else if (questionType === 'multi_select') {{
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="checkbox" disabled><label class="form-check-label">Option 1</label></div>';
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="checkbox" disabled><label class="form-check-label">Option 2</label></div>';
                    }} else if (questionType === 'scale') {{
                        previewHtml += '<input type="range" class="form-range" min="1" max="5" disabled><div class="d-flex justify-content-between small"><span>1</span><span>5</span></div>';
                    }} else if (questionType === 'text') {{
                        previewHtml += '<input type="text" class="form-control" placeholder="User types here..." disabled>';
                    }}
                    
                    preview.innerHTML = previewHtml;
                }} else {{
                    preview.innerHTML = '<em>Fill out the form to see preview</em>';
                }}
            }}
            
            // Update preview on input
            document.querySelector('[name="question_text"]').addEventListener('input', updatePreview);
            document.querySelector('[name="question_type"]').addEventListener('change', updatePreview);
        </script>
    </body>
    </html>
    """)

@admin_router.post("/questions")
async def create_question(
    request: Request,
    id: str = Form(...),
    question_text: str = Form(...),
    category: str = Form(...),
    question_type: str = Form(...),
    profile_field: str = Form(...),
    priority: int = Form(...),
    app_context: str = Form(...),
    options: str = Form(""),
    is_active: Optional[str] = Form(None),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    try:
        # Parse app_context JSON
        import json
        app_context_json = json.loads(app_context) if app_context else []
        
        # Parse options JSON if provided
        options_json = json.loads(options) if options else None
        
        # Convert is_active checkbox
        is_active_bool = is_active is not None
        
        # Insert question
        await db.execute(
            """
            INSERT INTO profiling_questions 
            (id, category, question_text, question_type, profile_field, priority, app_context, options, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9)
            """,
            id, category, question_text, question_type, profile_field, priority,
            json.dumps(app_context_json), json.dumps(options_json) if options_json else None, is_active_bool
        )
        
        return RedirectResponse(url="/admin/questions?created=1", status_code=302)
        
    except Exception as e:
        # Handle errors (duplicate ID, invalid JSON, etc.)
        return HTMLResponse(f"""
            <script>
                alert('Error creating question: {str(e)}');
                window.history.back();
            </script>
        """)

@admin_router.get("/questions/{question_id}/edit", response_class=HTMLResponse)
async def edit_question_form(
    request: Request,
    question_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Get existing question
    question = await db.fetch_one(
        "SELECT * FROM profiling_questions WHERE id = $1", question_id
    )
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Convert JSONB fields to strings for the form
    import json
    app_context_str = json.dumps(question["app_context"]) if question["app_context"] else '[]'
    options_str = json.dumps(question["options"]) if question["options"] else ''
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Question - fairydust Admin</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-edit me-2"></i>Edit Question</h1>
                <a href="/admin/questions" class="btn btn-secondary">← Back to Questions</a>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <form method="post" action="/admin/questions/{question_id}/update">
                        <div class="row">
                            <div class="col-md-8">
                                <div class="mb-3">
                                    <label class="form-label">Question ID</label>
                                    <input type="text" class="form-control" value="{question["id"]}" disabled>
                                    <div class="form-text">Question ID cannot be changed</div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Question Text</label>
                                    <textarea class="form-control" name="question_text" rows="3" required>{question["question_text"]}</textarea>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Category</label>
                                            <input type="text" class="form-control" name="category" required value="{question["category"]}">
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Question Type</label>
                                            <select class="form-select" name="question_type" required onchange="updateOptionsSection()">
                                                <option value="single_choice" {'selected' if question["question_type"] == 'single_choice' else ''}>Single Choice</option>
                                                <option value="multi_select" {'selected' if question["question_type"] == 'multi_select' else ''}>Multi Select</option>
                                                <option value="scale" {'selected' if question["question_type"] == 'scale' else ''}>Scale (1-5)</option>
                                                <option value="text" {'selected' if question["question_type"] == 'text' else ''}>Text Input</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Profile Field</label>
                                            <input type="text" class="form-control" name="profile_field" required value="{question["profile_field"]}">
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Priority</label>
                                            <input type="number" class="form-control" name="priority" value="{question["priority"]}" min="1" max="10" required>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">App Context</label>
                                    <input type="text" class="form-control" name="app_context" value='{app_context_str}'>
                                </div>
                                
                                <div id="optionsSection" style="display: {'block' if question["question_type"] in ['single_choice', 'multi_select', 'scale'] else 'none'};">
                                    <div class="mb-3">
                                        <label class="form-label">Options (JSON)</label>
                                        <textarea class="form-control" name="options" rows="6">{options_str}</textarea>
                                    </div>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" name="is_active" {'checked' if question["is_active"] else ''}>
                                    <label class="form-check-label">
                                        Active (show to users)
                                    </label>
                                </div>
                            </div>
                            
                            <div class="col-md-4">
                                <div class="card bg-light">
                                    <div class="card-header">
                                        <h6 class="mb-0">Preview</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="questionPreview">
                                            <strong>{question["question_text"]}</strong><br><br>
                                            <em>Update form to see preview changes</em>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <hr>
                        <div class="d-flex justify-content-end">
                            <a href="/admin/questions" class="btn btn-outline-secondary me-2">Cancel</a>
                            <button type="submit" class="btn btn-success">
                                <i class="fas fa-save"></i> Update Question
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function updateOptionsSection() {{
                const questionType = document.querySelector('[name="question_type"]').value;
                const optionsSection = document.getElementById('optionsSection');
                const optionsTextarea = document.querySelector('[name="options"]');
                
                if (questionType === 'single_choice' || questionType === 'multi_select') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                }} else if (questionType === 'scale') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                }} else {{
                    optionsSection.style.display = 'none';
                    optionsTextarea.required = false;
                }}
            }}
            
            // Update preview on input
            document.querySelector('[name="question_text"]').addEventListener('input', function() {{
                document.getElementById('questionPreview').innerHTML = '<strong>' + this.value + '</strong><br><br><em>Update form to see preview changes</em>';
            }});
        </script>
    </body>
    </html>
    """)

@admin_router.post("/questions/{question_id}/update")
async def update_question(
    request: Request,
    question_id: str,
    question_text: str = Form(...),
    category: str = Form(...),
    question_type: str = Form(...),
    profile_field: str = Form(...),
    priority: int = Form(...),
    app_context: str = Form(...),
    options: str = Form(""),
    is_active: Optional[str] = Form(None),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    try:
        # Parse JSON fields
        import json
        app_context_json = json.loads(app_context) if app_context else []
        options_json = json.loads(options) if options else None
        is_active_bool = is_active is not None
        
        # Update question
        await db.execute(
            """
            UPDATE profiling_questions 
            SET question_text = $1, category = $2, question_type = $3, profile_field = $4, 
                priority = $5, app_context = $6::jsonb, options = $7::jsonb, is_active = $8
            WHERE id = $9
            """,
            question_text, category, question_type, profile_field, priority,
            json.dumps(app_context_json), json.dumps(options_json) if options_json else None, 
            is_active_bool, question_id
        )
        
        return RedirectResponse(url="/admin/questions?updated=1", status_code=302)
        
    except Exception as e:
        return HTMLResponse(f"""
            <script>
                alert('Error updating question: {str(e)}');
                window.history.back();
            </script>
        """)

@admin_router.post("/questions/{question_id}/toggle")
async def toggle_question(
    question_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Get current status
    question = await db.fetch_one("SELECT is_active FROM profiling_questions WHERE id = $1", question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Toggle status
    new_status = not question["is_active"]
    await db.execute(
        "UPDATE profiling_questions SET is_active = $1 WHERE id = $2",
        new_status, question_id
    )
    
    return RedirectResponse(url="/admin/questions", status_code=302)

@admin_router.post("/questions/{question_id}/delete")
async def delete_question(
    question_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Check if question has responses
    response_count = await db.fetch_one(
        "SELECT COUNT(*) as count FROM user_question_responses WHERE question_id = $1",
        question_id
    )
    
    if response_count["count"] > 0:
        return HTMLResponse("""
            <script>
                alert('Cannot delete question with existing responses. Disable it instead.');
                window.location.href = '/admin/questions';
            </script>
        """)
    
    # Delete question
    await db.execute("DELETE FROM profiling_questions WHERE id = $1", question_id)
    
    return RedirectResponse(url="/admin/questions?deleted=1", status_code=302)

# ============================================================================
# LLM MANAGEMENT ROUTES
# ============================================================================

@admin_router.get("/llm", response_class=HTMLResponse)
async def llm_dashboard(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """LLM analytics and configuration dashboard"""
    
    # Get total usage stats (last 30 days)
    stats = await db.fetch_one("""
        SELECT 
            COUNT(*) as total_requests,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as avg_latency_ms
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '30 days'
    """)
    
    # Get model breakdown
    model_stats = await db.fetch_all("""
        SELECT 
            provider,
            model_id,
            COUNT(*) as requests,
            SUM(cost_usd) as cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY provider, model_id
        ORDER BY cost DESC
        LIMIT 10
    """)
    
    # Get app configurations
    app_configs = await db.fetch_all("""
        SELECT c.*, a.name as app_name
        FROM app_model_configs c
        JOIN apps a ON c.app_id = a.id
        ORDER BY c.updated_at DESC
    """)
    
    # Build model stats HTML
    model_stats_html = ""
    for stat in model_stats:
        model_stats_html += f"""
        <tr>
            <td>{stat['provider']}</td>
            <td>{stat['model_id']}</td>
            <td>{stat['requests']:,}</td>
            <td>${stat['cost']:.4f}</td>
            <td>{stat['avg_latency']:.0f}ms</td>
        </tr>
        """
    
    # Build app configs HTML
    app_configs_html = ""
    for config in app_configs:
        app_configs_html += f"""
        <tr>
            <td><strong>{config['app_name'] or config['app_id']}</strong></td>
            <td>{config['primary_provider']}</td>
            <td>{config['primary_model_id']}</td>
            <td>
                <a href="/admin/llm/apps/{config['app_id']}" class="btn btn-sm btn-primary">
                    <i class="fas fa-cog"></i> Configure
                </a>
            </td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LLM Management - fairydust Admin</title>
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
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-brain me-2"></i>LLM Management</h1>
                <a href="/admin/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
            </div>
            
            <!-- Stats Cards -->
            <div class="row mb-4">
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-primary h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Requests (30d)</div>
                                    <div class="h5 mb-0">{stats['total_requests'] or 0:,}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-comments fa-2x text-muted"></i>
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
                                    <div class="text-uppercase mb-1">Total Tokens</div>
                                    <div class="h5 mb-0">{stats['total_tokens'] or 0:,}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-coins fa-2x text-muted"></i>
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
                                    <div class="text-uppercase mb-1">Total Cost</div>
                                    <div class="h5 mb-0">${stats['total_cost_usd'] or 0:.2f}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-dollar-sign fa-2x text-muted"></i>
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
                                    <div class="text-uppercase mb-1">Avg Latency</div>
                                    <div class="h5 mb-0">{stats['avg_latency_ms'] or 0:.0f}ms</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-clock fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <!-- Model Performance -->
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0">Top Models by Cost (30 days)</h6>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>Provider</th>
                                            <th>Model</th>
                                            <th>Requests</th>
                                            <th>Cost</th>
                                            <th>Avg Latency</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {model_stats_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- App Configurations -->
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0">App Model Configurations</h6>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>App</th>
                                            <th>Provider</th>
                                            <th>Model</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {app_configs_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """)

@admin_router.get("/llm/apps/{app_id}", response_class=HTMLResponse)
async def llm_app_config(
    request: Request,
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """LLM configuration interface for specific app"""
    
    # Get app details
    app = await db.fetch_one("""
        SELECT id, name, slug FROM apps WHERE id = $1 OR slug = $1
    """, app_id)
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    # Get current model configuration
    config = await db.fetch_one("""
        SELECT * FROM app_model_configs WHERE app_id = $1
    """, app['id'])
    
    if not config:
        # Create default config if none exists
        # Create default config based on app type
        default_provider = 'anthropic'
        default_model = 'claude-3-5-haiku-20241022'
        default_params = '{"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}'
        default_fallbacks = '[{"provider": "openai", "model_id": "gpt-4o-mini", "trigger": "provider_error", "parameters": {"temperature": 0.8, "max_tokens": 150}}]'
        default_cost_limits = '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'
        
        if app['slug'] == 'fairydust-recipe':
            default_model = 'claude-3-5-sonnet-20241022'
            default_params = '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}'
            default_fallbacks = '[{"provider": "openai", "model_id": "gpt-4o", "trigger": "provider_error", "parameters": {"temperature": 0.7, "max_tokens": 1000}}, {"provider": "openai", "model_id": "gpt-4o-mini", "trigger": "cost_threshold_exceeded", "parameters": {"temperature": 0.7, "max_tokens": 1000}}]'
            default_cost_limits = '{"per_request_max": 0.15, "daily_max": 25.0, "monthly_max": 200.0}'
        
        await db.execute("""
            INSERT INTO app_model_configs (
                app_id, primary_provider, primary_model_id, primary_parameters,
                fallback_models, cost_limits, feature_flags
            ) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb)
        """, 
            app['id'], default_provider, default_model, default_params,
            default_fallbacks, default_cost_limits,
            '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'
        )
        
        config = await db.fetch_one("""
            SELECT * FROM app_model_configs WHERE app_id = $1
        """, app['id'])
    
    import json
    
    # Available models by provider
    available_models = {
        'anthropic': [
            'claude-3-5-sonnet-20241022',
            'claude-3-5-haiku-20241022',
            'claude-3-sonnet-20240229',
            'claude-3-haiku-20240307',
            'claude-3-opus-20240229'
        ],
        'openai': [
            'gpt-4o',
            'gpt-4o-mini',
            'gpt-4-turbo',
            'gpt-4-turbo-preview',
            'gpt-4',
            'gpt-3.5-turbo',
            'gpt-3.5-turbo-16k'
        ]
    }
    
    config_json = {
        'primary_provider': config['primary_provider'],
        'primary_model_id': config['primary_model_id'],
        'primary_parameters': config['primary_parameters'],
        'fallback_models': config['fallback_models'],
        'cost_limits': config['cost_limits'],
        'feature_flags': config['feature_flags']
    }
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Configure {app['name']} - fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
            .json-preview {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 0.375rem; padding: 1rem; }}
            .fallback-model {{ border: 1px solid #dee2e6; border-radius: 0.375rem; padding: 1rem; margin-bottom: 1rem; }}
        </style>
    </head>
    <body class="bg-light">
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust me-2"></i>fairydust Admin
                </a>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-cog me-2"></i>Configure {app['name']}</h1>
                <a href="/admin/llm" class="btn btn-secondary">← Back to LLM Dashboard</a>
            </div>
            
            <div class="row">
                <div class="col-lg-8">
                    <form id="configForm" method="post" action="/admin/llm/apps/{app['id']}/update">
                        <!-- Primary Model Configuration -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-brain me-2"></i>Primary Model</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Provider</label>
                                            <select class="form-select" name="primary_provider" required>
                                                <option value="anthropic" {'selected' if config['primary_provider'] == 'anthropic' else ''}>Anthropic</option>
                                                <option value="openai" {'selected' if config['primary_provider'] == 'openai' else ''}>OpenAI</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Model ID</label>
                                            <select class="form-select" name="primary_model_id" id="primary_model_id" required>
                                                <!-- Options will be populated by JavaScript -->
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Temperature</label>
                                            <input type="number" class="form-control" name="temperature" 
                                                   value="{config['primary_parameters'].get('temperature', 0.8)}" 
                                                   min="0" max="2" step="0.1">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Max Tokens</label>
                                            <input type="number" class="form-control" name="max_tokens" 
                                                   value="{config['primary_parameters'].get('max_tokens', 150)}" 
                                                   min="1" max="4000">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Top P</label>
                                            <input type="number" class="form-control" name="top_p" 
                                                   value="{config['primary_parameters'].get('top_p', 0.9)}" 
                                                   min="0" max="1" step="0.1">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Fallback Models -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-shield-alt me-2"></i>Fallback Models</h5>
                            </div>
                            <div class="card-body">
                                <div id="fallback-models-container">
                                    <!-- Fallback models will be populated by JavaScript -->
                                </div>
                                <button type="button" class="btn btn-outline-primary btn-sm" onclick="addFallbackModel()">
                                    <i class="fas fa-plus me-2"></i>Add Fallback Model
                                </button>
                            </div>
                        </div>
                        
                        <!-- Cost Limits -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-dollar-sign me-2"></i>Cost Limits</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Per Request Max ($)</label>
                                            <input type="number" class="form-control" name="per_request_max" 
                                                   value="{config['cost_limits'].get('per_request_max', 0.05)}" 
                                                   min="0" step="0.01">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Daily Max ($)</label>
                                            <input type="number" class="form-control" name="daily_max" 
                                                   value="{config['cost_limits'].get('daily_max', 10.0)}" 
                                                   min="0" step="0.01">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Monthly Max ($)</label>
                                            <input type="number" class="form-control" name="monthly_max" 
                                                   value="{config['cost_limits'].get('monthly_max', 100.0)}" 
                                                   min="0" step="0.01">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Feature Flags -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-flag me-2"></i>Feature Flags</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="streaming_enabled" 
                                                   {'checked' if config['feature_flags'].get('streaming_enabled', True) else ''}>
                                            <label class="form-check-label">Streaming Enabled</label>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="cache_responses" 
                                                   {'checked' if config['feature_flags'].get('cache_responses', True) else ''}>
                                            <label class="form-check-label">Cache Responses</label>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="log_prompts" 
                                                   {'checked' if config['feature_flags'].get('log_prompts', False) else ''}>
                                            <label class="form-check-label">Log Prompts</label>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="d-grid gap-2">
                            <button type="submit" class="btn btn-primary btn-lg">
                                <i class="fas fa-save me-2"></i>Update Configuration
                            </button>
                        </div>
                    </form>
                </div>
                
                <div class="col-lg-4">
                    <!-- Current Configuration Preview -->
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="fas fa-code me-2"></i>Current Configuration</h5>
                        </div>
                        <div class="card-body">
                            <div class="json-preview">
                                <pre><code>{json.dumps(config_json, indent=2)}</code></pre>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Available models data
            const availableModels = {json.dumps(available_models)};
            const currentConfig = {json.dumps(config_json)};
            
            let fallbackCounter = 0;
            
            // Initialize form
            document.addEventListener('DOMContentLoaded', function() {{
                updateModelDropdown('primary_provider', 'primary_model_id', currentConfig.primary_model_id);
                loadFallbackModels();
                
                // Add event listener for provider change
                document.querySelector('select[name="primary_provider"]').addEventListener('change', function() {{
                    updateModelDropdown('primary_provider', 'primary_model_id');
                }});
            }});
            
            function updateModelDropdown(providerSelectId, modelSelectId, selectedModel = '') {{
                const providerSelect = document.querySelector(`select[name="${{providerSelectId}}"]`);
                const modelSelect = document.querySelector(`select[name="${{modelSelectId}}"], #${{modelSelectId}}`);
                const provider = providerSelect.value;
                
                // Clear existing options
                modelSelect.innerHTML = '';
                
                // Add models for selected provider
                if (availableModels[provider]) {{
                    availableModels[provider].forEach(model => {{
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        if (model === selectedModel) {{
                            option.selected = true;
                        }}
                        modelSelect.appendChild(option);
                    }});
                }}
            }}
            
            function loadFallbackModels() {{
                const container = document.getElementById('fallback-models-container');
                container.innerHTML = '';
                
                if (currentConfig.fallback_models && currentConfig.fallback_models.length > 0) {{
                    currentConfig.fallback_models.forEach((fallback, index) => {{
                        addFallbackModelElement(fallback, index);
                    }});
                }}
            }}
            
            function addFallbackModel() {{
                addFallbackModelElement({{
                    provider: 'openai',
                    model_id: 'gpt-3.5-turbo',
                    trigger: 'provider_error',
                    parameters: {{ temperature: 0.8, max_tokens: 150 }}
                }}, fallbackCounter++);
            }}
            
            function addFallbackModelElement(fallback, index) {{
                const container = document.getElementById('fallback-models-container');
                const fallbackDiv = document.createElement('div');
                fallbackDiv.className = 'fallback-model mb-3';
                fallbackDiv.innerHTML = `
                    <div class="row g-2">
                        <div class="col-md-3">
                            <label class="form-label">Provider</label>
                            <select class="form-select" name="fallback_provider_${{index}}" onchange="updateModelDropdown('fallback_provider_${{index}}', 'fallback_model_${{index}}')">
                                <option value="anthropic" ${{fallback.provider === 'anthropic' ? 'selected' : ''}}>Anthropic</option>
                                <option value="openai" ${{fallback.provider === 'openai' ? 'selected' : ''}}>OpenAI</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Model</label>
                            <select class="form-select" name="fallback_model_${{index}}" id="fallback_model_${{index}}">
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Trigger</label>
                            <select class="form-select" name="fallback_trigger_${{index}}">
                                <option value="provider_error" ${{fallback.trigger === 'provider_error' ? 'selected' : ''}}>Provider Error</option>
                                <option value="cost_threshold_exceeded" ${{fallback.trigger === 'cost_threshold_exceeded' ? 'selected' : ''}}>Cost Threshold Exceeded</option>
                                <option value="rate_limit" ${{fallback.trigger === 'rate_limit' ? 'selected' : ''}}>Rate Limit</option>
                                <option value="model_unavailable" ${{fallback.trigger === 'model_unavailable' ? 'selected' : ''}}>Model Unavailable</option>
                            </select>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label">Temperature</label>
                            <input type="number" class="form-control" name="fallback_temperature_${{index}}" 
                                   value="${{fallback.parameters?.temperature || 0.8}}" min="0" max="2" step="0.1">
                        </div>
                        <div class="col-md-1 d-flex align-items-end">
                            <button type="button" class="btn btn-outline-danger btn-sm" onclick="removeFallbackModel(this)">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
                container.appendChild(fallbackDiv);
                
                // Update model dropdown for this fallback
                setTimeout(() => {{
                    updateModelDropdown(`fallback_provider_${{index}}`, `fallback_model_${{index}}`, fallback.model_id);
                }}, 10);
                
                fallbackCounter = Math.max(fallbackCounter, index + 1);
            }}
            
            function removeFallbackModel(button) {{
                button.closest('.fallback-model').remove();
            }}
            
            // Form submission handler
            document.getElementById('configForm').addEventListener('submit', function(e) {{
                // Collect fallback models data
                const fallbackModels = [];
                const fallbackElements = document.querySelectorAll('.fallback-model');
                
                fallbackElements.forEach((element, index) => {{
                    const provider = element.querySelector(`select[name^="fallback_provider_"]`).value;
                    const modelId = element.querySelector(`select[name^="fallback_model_"]`).value;
                    const trigger = element.querySelector(`select[name^="fallback_trigger_"]`).value;
                    const temperature = parseFloat(element.querySelector(`input[name^="fallback_temperature_"]`).value);
                    
                    fallbackModels.push({{
                        provider: provider,
                        model_id: modelId,
                        trigger: trigger,
                        parameters: {{
                            temperature: temperature,
                            max_tokens: parseInt(document.querySelector('input[name="max_tokens"]').value)
                        }}
                    }});
                }});
                
                // Add hidden input for fallback models
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'fallback_models_json';
                hiddenInput.value = JSON.stringify(fallbackModels);
                this.appendChild(hiddenInput);
            }});
        </script>
    </body>
    </html>
    """)

@admin_router.post("/llm/apps/{app_id}/update")
async def update_llm_app_config(
    app_id: str,
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """Update LLM configuration for an app"""
    
    # Get app details
    app = await db.fetch_one("""
        SELECT id, name, slug FROM apps WHERE id = $1 OR slug = $1
    """, app_id)
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    # Get form data
    form = await request.form()
    
    # Parse fallback models from JSON if provided
    fallback_models = []
    if form.get("fallback_models_json"):
        import json
        try:
            fallback_models = json.loads(form.get("fallback_models_json"))
        except json.JSONDecodeError:
            fallback_models = []
    
    # Make API call to Apps service to update configuration
    apps_service_url = os.getenv("APPS_SERVICE_URL", "http://apps:8003")
    
    # Build update payload
    update_data = {
        "primary_provider": form.get("primary_provider"),
        "primary_model_id": form.get("primary_model_id"),
        "primary_parameters": {
            "temperature": float(form.get("temperature", 0.8)),
            "max_tokens": int(form.get("max_tokens", 150)),
            "top_p": float(form.get("top_p", 0.9))
        },
        "fallback_models": fallback_models,
        "cost_limits": {
            "per_request_max": float(form.get("per_request_max", 0.05)),
            "daily_max": float(form.get("daily_max", 10.0)),
            "monthly_max": float(form.get("monthly_max", 100.0))
        },
        "feature_flags": {
            "streaming_enabled": "streaming_enabled" in form,
            "cache_responses": "cache_responses" in form,
            "log_prompts": "log_prompts" in form
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get admin token for API call
            admin_token = request.cookies.get("admin_token")
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            response = await client.put(
                f"{apps_service_url}/llm/{app['id']}/model-config",
                json=update_data,
                headers=headers
            )
            
            if response.status_code == 200:
                return RedirectResponse(
                    url=f"/admin/llm/apps/{app_id}?updated=1",
                    status_code=302
                )
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to update configuration: {response.text}"
                )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating configuration: {str(e)}"
        )
    
    return RedirectResponse(
        url=f"/admin/llm/apps/{app_id}?error=1",
        status_code=302
    )