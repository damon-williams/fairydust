import os
import sys
from typing import Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from auth import BuilderAuth, get_current_builder_user, optional_builder_user

from shared.database import Database, get_db
from shared.redis_client import get_redis

builder_router = APIRouter()

IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://identity:8001")


@builder_router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request, builder_user: Optional[dict] = Depends(optional_builder_user)
):
    if builder_user:
        return RedirectResponse(url="/builder/dashboard", status_code=302)

    return HTMLResponse(
        """
    <!DOCTYPE html>
    <html>
    <head>
        <title>fairydust Builder Login</title>
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
                                <h1><i class="fas fa-hammer fairy-dust fs-1"></i></h1>
                                <h2 class="h4">fairydust</h2>
                                <p class="text-muted">Builder Portal</p>
                            </div>

                            <form method="post" action="/builder/login" id="loginForm">
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
                                        Log in
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
                    const response = await fetch('/builder/request-otp', { method: 'POST', body: formData });
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


@builder_router.post("/login")
async def login(
    request: Request,
    identifier: str = Form(...),
    otp: str = Form(...),
    db: Database = Depends(get_db),
):
    # Verify user exists and is active
    identifier_type = "email" if "@" in identifier else "phone"
    user = await db.fetch_one(
        f"SELECT * FROM users WHERE {identifier_type} = $1 AND is_active = true", identifier
    )

    if not user:
        return HTMLResponse(
            """
            <script>
                alert('User not found or inactive. Please register first.');
                window.location.href = '/builder/login';
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
                        window.location.href = '/builder/login';
                    </script>
                """
                )
        except Exception:
            return HTMLResponse(
                """
                <script>
                    alert('Authentication service unavailable');
                    window.location.href = '/builder/login';
                </script>
            """
            )

    # Create builder session
    redis_client = await get_redis()
    auth = BuilderAuth(redis_client)
    session_token = await auth.create_builder_session(str(user["id"]), user["fairyname"])

    # Set session cookie and redirect
    response = RedirectResponse(url="/builder/dashboard", status_code=302)
    response.set_cookie(
        key="builder_session",
        value=session_token,
        httponly=True,
        secure=True if os.getenv("ENVIRONMENT") == "production" else False,
        samesite="lax",
        max_age=8 * 3600,  # 8 hours
    )

    return response


@builder_router.post("/request-otp")
async def request_otp(identifier: str = Form(...)):
    """Request OTP for builder login"""
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


@builder_router.get("/logout")
async def logout(builder_user: dict = Depends(get_current_builder_user)):
    redis_client = await get_redis()
    auth = BuilderAuth(redis_client)
    await auth.revoke_builder_session(builder_user["user_id"])

    response = RedirectResponse(url="/builder/login", status_code=302)
    response.delete_cookie("builder_session")
    return response


@builder_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    builder_user: dict = Depends(get_current_builder_user),
    db: Database = Depends(get_db),
):
    # Get builder's apps and stats
    apps = await db.fetch_all(
        """
        SELECT id, name, status, is_active, category, created_at, updated_at
        FROM apps
        WHERE builder_id = $1
        ORDER BY created_at DESC
        """,
        builder_user["user_id"],
    )

    # Get usage statistics
    total_apps = len(apps)
    active_apps = len([app for app in apps if app["status"] == "approved" and app["is_active"]])
    pending_apps = len([app for app in apps if app["status"] == "pending"])

    # Get recent transactions for this builder's apps
    app_ids = [str(app["id"]) for app in apps] if apps else ["00000000-0000-0000-0000-000000000000"]
    recent_transactions = await db.fetch_all(
        """
        SELECT dt.amount, dt.created_at, dt.description, u.fairyname as user_name
        FROM dust_transactions dt
        JOIN users u ON dt.user_id = u.id
        WHERE dt.app_id = ANY($1::uuid[])
        ORDER BY dt.created_at DESC
        LIMIT 5
        """,
        app_ids,
    )

    # Generate apps HTML
    apps_html = ""
    for app in apps:
        # Show appropriate badge based on status
        if app["status"] == "approved" and app["is_active"]:
            status_html = '<span class="badge bg-success">Active</span>'
        elif app["status"] == "suspended":
            status_html = '<span class="badge bg-danger">Suspended</span>'
        elif app["status"] == "rejected":
            status_html = '<span class="badge bg-danger">Rejected</span>'
        else:
            status_html = '<span class="badge bg-success">Active</span>'  # Default to active for new instant approval

        apps_html += f"""
        <div class="col-md-6 col-lg-4 mb-3">
            <div class="card h-100">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <h6 class="card-title">{app["name"]}</h6>
                        {status_html}
                    </div>
                    <p class="text-muted small">Category: {app["category"].title()}</p>
                    <div class="bg-light p-2 rounded mb-2">
                        <small class="text-muted">App ID:</small><br>
                        <code style="font-size: 0.85rem;">{str(app["id"])}</code>
                    </div>
                    <p class="text-muted small">Created: {app["created_at"].strftime('%m/%d/%Y')}</p>
                </div>
                <div class="card-footer">
                    <button class="btn btn-sm btn-outline-primary" onclick="copyAppId('{str(app["id"])}', this)">Copy App ID</button>
                </div>
            </div>
        </div>
        """

    # Generate transactions HTML
    transactions_html = ""
    for tx in recent_transactions:
        transactions_html += f"""
        <tr>
            <td>{tx["user_name"]}</td>
            <td><span class="fairy-dust">{tx["amount"]}</span></td>
            <td>{tx["description"]}</td>
            <td><small class="text-muted">{tx["created_at"].strftime('%m/%d %H:%M')}</small></td>
        </tr>
        """

    return HTMLResponse(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Builder Dashboard - Fairydust</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
            .stat-card {{ border-left: 4px solid; }}
            .stat-card-primary {{ border-left-color: #4e73df; }}
            .stat-card-success {{ border-left-color: #1cc88a; }}
            .stat-card-warning {{ border-left-color: #f6c23e; }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/builder/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {builder_user['fairyname']}</span>
                    <a class="nav-link" href="/builder/logout">Logout</a>
                </div>
            </div>
        </nav>

        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1>Builder Dashboard</h1>
                <a href="/builder/apps/new" class="btn btn-success">
                    <i class="fas fa-plus me-2"></i>Register New App
                </a>
            </div>

            <!-- Stats Cards -->
            <div class="row mb-4">
                <div class="col-xl-4 col-md-6 mb-4">
                    <div class="card stat-card stat-card-primary h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Apps</div>
                                    <div class="h5 mb-0">{total_apps}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-mobile-alt fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-xl-4 col-md-6 mb-4">
                    <div class="card stat-card stat-card-success h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Active Apps</div>
                                    <div class="h5 mb-0">{active_apps}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-check fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-xl-4 col-md-6 mb-4">
                    <div class="card stat-card stat-card-warning h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Pending Review</div>
                                    <div class="h5 mb-0">{pending_apps}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-clock fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Your Apps -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0">Your Apps</h5>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                {apps_html if apps_html else '<div class="col-12"><p class="text-muted text-center">No apps yet. <a href="/builder/apps/new">Submit your first app!</a></p></div>'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Recent Activity -->
            <div class="row">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0">Recent App Usage</h5>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>User</th>
                                            <th>DUST</th>
                                            <th>App</th>
                                            <th>When</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {transactions_html if transactions_html else '<tr><td colspan="4" class="text-center text-muted">No recent activity</td></tr>'}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function copyAppId(appId, button) {{
                navigator.clipboard.writeText(appId).then(function() {{
                    showCopyFeedback();
                }}).catch(function() {{
                    // Fallback for older browsers
                    const textArea = document.createElement('textarea');
                    textArea.value = appId;
                    document.body.appendChild(textArea);
                    textArea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textArea);
                    showCopyFeedback();
                }});

                function showCopyFeedback() {{
                    const feedback = document.getElementById('copyFeedback');
                    if (feedback) {{
                        feedback.style.display = 'inline';
                        setTimeout(() => {{
                            feedback.style.display = 'none';
                        }}, 2000);
                    }}
                }}
            }}
        </script>
    </body>
    </html>
    """
    )


@builder_router.get("/apps/new", response_class=HTMLResponse)
async def new_app_form(request: Request, builder_user: dict = Depends(get_current_builder_user)):
    return HTMLResponse(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Submit New App - Fairydust Builder</title>
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
                <a class="navbar-brand" href="/builder/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {builder_user['fairyname']}</span>
                    <a class="nav-link" href="/builder/logout">Logout</a>
                </div>
            </div>
        </nav>

        <div class="container mt-4">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header">
                            <div class="d-flex justify-content-between align-items-center">
                                <h5 class="mb-0">Submit New App</h5>
                                <a href="/builder/dashboard" class="btn btn-secondary btn-sm">← Back</a>
                            </div>
                        </div>
                        <div class="card-body">
                            <form method="post" action="/builder/apps/new">
                                <div class="mb-3">
                                    <label for="name" class="form-label">App Name <span class="text-danger">*</span></label>
                                    <input type="text" class="form-control" id="name" name="name" required maxlength="255">
                                </div>


                                <div class="mb-3">
                                    <label for="description" class="form-label">Description <span class="text-danger">*</span></label>
                                    <textarea class="form-control" id="description" name="description" rows="4" required maxlength="1000"></textarea>
                                </div>

                                <div class="mb-3">
                                    <label for="category" class="form-label">Category <span class="text-danger">*</span></label>
                                    <select class="form-select" id="category" name="category" required>
                                        <option value="">Select a category</option>
                                        <option value="productivity">Productivity</option>
                                        <option value="entertainment">Entertainment</option>
                                        <option value="education">Education</option>
                                        <option value="business">Business</option>
                                        <option value="creative">Creative</option>
                                        <option value="utilities">Utilities</option>
                                        <option value="games">Games</option>
                                        <option value="other">Other</option>
                                    </select>
                                </div>

                                <div class="mb-3">
                                    <label for="website_url" class="form-label">Website URL</label>
                                    <input type="url" class="form-control" id="website_url" name="website_url" placeholder="https://your-app.com">
                                </div>

                                <div class="mb-3">
                                    <label for="demo_url" class="form-label">Demo URL</label>
                                    <input type="url" class="form-control" id="demo_url" name="demo_url" placeholder="https://demo.your-app.com">
                                </div>

                                <div class="mb-3">
                                    <label for="icon_url" class="form-label">Icon URL</label>
                                    <input type="url" class="form-control" id="icon_url" name="icon_url" placeholder="https://your-app.com/icon.png">
                                    <div class="form-text">PNG or JPG, recommended 256x256px</div>
                                </div>

                                <div class="d-grid">
                                    <button type="submit" class="btn btn-primary">Register App</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    )


@builder_router.post("/apps/new")
async def submit_new_app(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    website_url: Optional[str] = Form(None),
    demo_url: Optional[str] = Form(None),
    icon_url: Optional[str] = Form(None),
    builder_user: dict = Depends(get_current_builder_user),
    db: Database = Depends(get_db),
):
    # Generate slug from name
    import re

    slug = re.sub(r"[^a-z0-9\s-]", "", name.lower()).replace(" ", "-")
    slug = re.sub(r"-+", "-", slug).strip("-")

    # Ensure slug uniqueness by appending numbers if needed
    base_slug = slug
    counter = 1
    while True:
        existing_app = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", slug)
        if not existing_app:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Create new app (immediately active)
    app_id = uuid4()
    await db.execute(
        """
        INSERT INTO apps (id, builder_id, name, slug, description, category, website_url, demo_url, icon_url, status, is_active)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'approved', true)
        """,
        app_id,
        builder_user["user_id"],
        name,
        slug,
        description,
        category,
        website_url or None,
        demo_url or None,
        icon_url or None,
    )

    return RedirectResponse(url=f"/builder/app-success/{app_id}", status_code=302)


@builder_router.get("/app-success/{app_id}", response_class=HTMLResponse)
async def app_success(
    request: Request,
    app_id: UUID,
    builder_user: dict = Depends(get_current_builder_user),
    db: Database = Depends(get_db),
):
    # Get the app details
    app = await db.fetch_one(
        "SELECT * FROM apps WHERE id = $1 AND builder_id = $2", app_id, builder_user["user_id"]
    )

    if not app:
        return RedirectResponse(url="/builder/dashboard", status_code=302)

    return HTMLResponse(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>App Registered Successfully - Fairydust Builder</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
            .success-card {{ border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }}
            .app-id-box {{ background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 10px; padding: 20px; font-family: monospace; font-size: 1.2rem; }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/builder/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {builder_user['fairyname']}</span>
                    <a class="nav-link" href="/builder/logout">Logout</a>
                </div>
            </div>
        </nav>

        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card success-card">
                        <div class="card-body text-center py-5">
                            <i class="fas fa-check-circle text-success mb-4" style="font-size: 4rem;"></i>
                            <h2 class="mb-4">App Registered Successfully!</h2>
                            <p class="lead mb-4">Your app "{app['name']}" is now live and ready to earn DUST.</p>

                            <div class="app-id-box mb-4">
                                <p class="mb-2"><strong>Your App ID:</strong></p>
                                <div class="d-flex align-items-center justify-content-center">
                                    <span id="appId">{str(app['id'])}</span>
                                    <button class="btn btn-sm btn-outline-primary ms-3" onclick="copyAppId('{str(app['id'])}', this)">
                                        <i class="fas fa-copy"></i> Copy
                                    </button>
                                    <span id="copyFeedback" class="text-success ms-2" style="display: none;">Copied!</span>
                                </div>
                            </div>


                            <div class="d-grid gap-2 d-md-block">
                                <a href="/builder/dashboard" class="btn btn-primary">
                                    <i class="fas fa-tachometer-alt me-2"></i>Go to Dashboard
                                </a>
                                <a href="/builder/apps/new" class="btn btn-outline-primary">
                                    <i class="fas fa-plus me-2"></i>Register Another App
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function copyAppId(appId, button) {{
                navigator.clipboard.writeText(appId).then(function() {{
                    showCopyFeedback();
                }}).catch(function() {{
                    // Fallback for older browsers
                    const textArea = document.createElement('textarea');
                    textArea.value = appId;
                    document.body.appendChild(textArea);
                    textArea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textArea);
                    showCopyFeedback();
                }});

                function showCopyFeedback() {{
                    const feedback = document.getElementById('copyFeedback');
                    if (feedback) {{
                        feedback.style.display = 'inline';
                        setTimeout(() => {{
                            feedback.style.display = 'none';
                        }}, 2000);
                    }}
                }}
            }}
        </script>
    </body>
    </html>
    """
    )
