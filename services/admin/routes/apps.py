from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
import httpx
import os

from shared.database import get_db, Database
from shared.redis_client import get_redis
from auth import AdminAuth, get_current_admin_user, optional_admin_user

apps_router = APIRouter()

@apps_router.get("/", response_class=HTMLResponse)
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

@apps_router.post("/{app_id}/approve")
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

@apps_router.post("/{app_id}/reject")
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

@apps_router.post("/{app_id}/suspend")
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

@apps_router.post("/{app_id}/reactivate")
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