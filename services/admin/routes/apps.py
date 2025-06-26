import uuid
from typing import Optional

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from shared.database import Database, get_db

apps_router = APIRouter()


@apps_router.get("/", response_class=HTMLResponse)
async def apps_list(
    request: Request,
    status_filter: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
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

    apps = await db.fetch_all(f"{base_query}{where_clause} ORDER BY a.created_at DESC", *params)

    # Fetch builders for the create form
    builders = await db.fetch_all(
        "SELECT id, fairyname, email FROM users WHERE is_builder = true ORDER BY fairyname"
    )

    # Build builder options for dropdown
    builder_options = ""
    for builder in builders:
        builder_options += (
            f'<option value="{builder["id"]}">{builder["fairyname"]} ({builder["email"]})</option>'
        )

    # Build category options
    categories = [
        ("productivity", "Productivity"),
        ("entertainment", "Entertainment"),
        ("education", "Education"),
        ("business", "Business"),
        ("creative", "Creative"),
        ("utilities", "Utilities"),
        ("games", "Games"),
        ("other", "Other"),
    ]
    category_options = ""
    for value, label in categories:
        category_options += f'<option value="{value}">{label}</option>'

    # Build success/error alerts
    alerts_html = ""
    if success:
        alerts_html += f'<div class="alert alert-success alert-dismissible fade show" role="alert">{success}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>'
    if error:
        alerts_html += f'<div class="alert alert-danger alert-dismissible fade show" role="alert">{error}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>'

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
        approve_btn = (
            f'<button class="btn btn-sm btn-success me-1" onclick="approveApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-check"></i></button>'
            if app["status"] == "pending"
            else ""
        )
        reject_btn = (
            f'<button class="btn btn-sm btn-danger me-1" onclick="rejectApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-times"></i></button>'
            if app["status"] == "pending"
            else ""
        )
        suspend_btn = (
            f'<button class="btn btn-sm btn-warning me-1" onclick="suspendApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-pause"></i></button>'
            if app["status"] == "approved"
            else ""
        )
        reactivate_btn = (
            f'<button class="btn btn-sm btn-info me-1" onclick="reactivateApp(\'{app["id"]}\', \'{app["name"]}\')"><i class="fas fa-play"></i></button>'
            if app["status"] == "suspended"
            else ""
        )

        apps_html += f"""
        <tr>
            <td><strong>{app["name"]}</strong><br><small class="text-muted">{app["description"][:100]}...</small></td>
            <td>{app["builder_name"]}<br><small class="text-muted">{app["builder_email"]}</small></td>
            <td><span class="text-capitalize">{app["category"]}</span></td>
            <td>{status_badge}</td>
            <td>{approve_btn}{reject_btn}{suspend_btn}{reactivate_btn}</td>
        </tr>
        """

    return HTMLResponse(
        f"""
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
                <div>
                    <button class="btn btn-primary me-2" type="button" data-bs-toggle="collapse" data-bs-target="#createAppForm" aria-expanded="false" aria-controls="createAppForm">
                        <i class="fas fa-plus me-2"></i>Create New App
                    </button>
                    <a href="/admin/dashboard" class="btn btn-secondary">← Back to Admin Dashboard</a>
                </div>
            </div>

            {alerts_html}

            <!-- Create App Form -->
            <div class="collapse mb-4" id="createAppForm">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="fas fa-plus me-2"></i>Create New App</h5>
                    </div>
                    <div class="card-body">
                        <form method="post" action="/admin/apps/">
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label for="name" class="form-label">App Name <span class="text-danger">*</span></label>
                                        <input type="text" class="form-control" id="name" name="name" required maxlength="255">
                                    </div>
                                    <div class="mb-3">
                                        <label for="slug" class="form-label">Slug <span class="text-danger">*</span></label>
                                        <input type="text" class="form-control" id="slug" name="slug" required maxlength="255"
                                               pattern="[a-z0-9-]+" title="Only lowercase letters, numbers, and hyphens allowed">
                                        <div class="form-text">Unique identifier (lowercase, hyphens allowed)</div>
                                    </div>
                                    <div class="mb-3">
                                        <label for="category" class="form-label">Category <span class="text-danger">*</span></label>
                                        <select class="form-select" id="category" name="category" required>
                                            <option value="">Select a category...</option>
                                            {category_options}
                                        </select>
                                    </div>
                                    <div class="mb-3">
                                        <label for="builder_id" class="form-label">Builder <span class="text-danger">*</span></label>
                                        <select class="form-select" id="builder_id" name="builder_id" required>
                                            <option value="">Select a builder...</option>
                                            {builder_options}
                                        </select>
                                    </div>
                                    <div class="mb-3">
                                        <label for="dust_per_use" class="form-label">DUST per Use</label>
                                        <input type="number" class="form-control" id="dust_per_use" name="dust_per_use" min="1" max="100" value="5">
                                        <div class="form-text">Cost in DUST tokens per app usage (default: 5)</div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label for="description" class="form-label">Description <span class="text-danger">*</span></label>
                                        <textarea class="form-control" id="description" name="description" required maxlength="1000" rows="4"></textarea>
                                    </div>
                                    <div class="mb-3">
                                        <label for="icon_url" class="form-label">Icon URL</label>
                                        <input type="url" class="form-control" id="icon_url" name="icon_url">
                                    </div>
                                    <div class="mb-3">
                                        <label for="website_url" class="form-label">Website URL</label>
                                        <input type="url" class="form-control" id="website_url" name="website_url">
                                    </div>
                                    <div class="mb-3">
                                        <label for="demo_url" class="form-label">Demo URL</label>
                                        <input type="url" class="form-control" id="demo_url" name="demo_url">
                                    </div>
                                    <div class="mb-3">
                                        <label for="callback_url" class="form-label">Callback URL</label>
                                        <input type="url" class="form-control" id="callback_url" name="callback_url">
                                    </div>
                                </div>
                            </div>
                            <div class="d-flex justify-content-end">
                                <button type="button" class="btn btn-secondary me-2" data-bs-toggle="collapse" data-bs-target="#createAppForm">Cancel</button>
                                <button type="submit" class="btn btn-primary">
                                    <i class="fas fa-save me-2"></i>Create App
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Apps List -->
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
    """
    )


@apps_router.post("/{app_id}/approve")
async def approve_app(
    app_id: str,
    admin_notes: str = Form(""),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    await db.execute(
        """
        UPDATE apps
        SET status = 'approved', is_active = true, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Approved by {admin_user['fairyname']}: {admin_notes}"
        if admin_notes
        else f"Approved by {admin_user['fairyname']}",
        app_id,
    )

    return RedirectResponse(url="/admin/apps", status_code=302)


@apps_router.post("/{app_id}/reject")
async def reject_app(
    app_id: str,
    admin_notes: str = Form(...),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    await db.execute(
        """
        UPDATE apps
        SET status = 'rejected', is_active = false, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Rejected by {admin_user['fairyname']}: {admin_notes}",
        app_id,
    )

    return RedirectResponse(url="/admin/apps", status_code=302)


@apps_router.post("/{app_id}/suspend")
async def suspend_app(
    app_id: str,
    admin_notes: str = Form(...),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    await db.execute(
        """
        UPDATE apps
        SET status = 'suspended', is_active = false, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Suspended by {admin_user['fairyname']}: {admin_notes}",
        app_id,
    )

    return RedirectResponse(url="/admin/apps", status_code=302)


@apps_router.post("/{app_id}/reactivate")
async def reactivate_app(
    app_id: str, admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
):
    await db.execute(
        """
        UPDATE apps
        SET status = 'approved', is_active = true, admin_notes = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        f"Reactivated by {admin_user['fairyname']}",
        app_id,
    )

    return RedirectResponse(url="/admin/apps", status_code=302)


@apps_router.post("/")
async def create_app(
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    builder_id: str = Form(...),
    dust_per_use: int = Form(5),
    icon_url: str = Form(""),
    website_url: str = Form(""),
    demo_url: str = Form(""),
    callback_url: str = Form(""),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    try:
        # Validate builder exists and is a builder
        builder = await db.fetch_one(
            "SELECT id, fairyname FROM users WHERE id = $1 AND is_builder = true", builder_id
        )
        if not builder:
            return RedirectResponse(
                url="/admin/apps?error=Invalid builder selected", status_code=302
            )

        # Check if slug already exists
        existing_app = await db.fetch_one("SELECT id FROM apps WHERE slug = $1", slug)
        if existing_app:
            return RedirectResponse(
                url="/admin/apps?error=App slug already exists", status_code=302
            )

        # Validate dust_per_use
        if dust_per_use < 1 or dust_per_use > 100:
            return RedirectResponse(
                url="/admin/apps?error=DUST per use must be between 1 and 100", status_code=302
            )

        # Create the app directly in the database
        app_id = uuid.uuid4()

        await db.execute(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
            app_id,
            uuid.UUID(builder_id),
            name,
            slug,
            description,
            icon_url if icon_url else None,
            dust_per_use,
            "approved",  # Apps are auto-approved per existing logic
            category,
            website_url if website_url else None,
            demo_url if demo_url else None,
            callback_url if callback_url else None,
            True,  # is_active = true for approved apps
            f"Created by admin {admin_user['fairyname']}",
        )

        return RedirectResponse(
            url=f"/admin/apps?success=App '{name}' created successfully for builder {builder['fairyname']}",
            status_code=302,
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error creating app: {e}")
        return RedirectResponse(
            url="/admin/apps?error=Failed to create app. Please try again.", status_code=302
        )
