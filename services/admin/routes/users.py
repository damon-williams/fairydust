from typing import Optional

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from shared.database import Database, get_db
from shared.json_utils import parse_jsonb_field

users_router = APIRouter()


@users_router.get("/", response_class=HTMLResponse)
async def users_list(
    request: Request,
    page: int = 1,
    search: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
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
        *params,
    )

    total_count = await db.fetch_one(f"{count_query}{where_clause}", *params)
    total_pages = (total_count["total"] + limit - 1) // limit

    users_html = ""
    for user in users:
        admin_badge = '<span class="badge bg-danger me-1">Admin</span>' if user["is_admin"] else ""
        builder_badge = '<span class="badge bg-info">Builder</span>' if user["is_builder"] else ""
        status_badge = (
            '<span class="badge bg-success">Active</span>'
            if user["is_active"]
            else '<span class="badge bg-secondary">Inactive</span>'
        )

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

    return HTMLResponse(
        f"""
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
    """
    )


# JSON API endpoint for React app
@users_router.get("")
async def get_users_json(
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get users list as JSON for React app"""
    offset = (page - 1) * limit

    # Build search query
    base_query = """
        SELECT id, fairyname, email, phone, is_builder, is_admin, is_active,
               dust_balance, created_at, updated_at, auth_provider, city, country,
               streak_days, metadata
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
        *params,
    )

    total_count = await db.fetch_one(f"{count_query}{where_clause}", *params)
    total_pages = (total_count["total"] + limit - 1) // limit

    # Format users for JSON response
    formatted_users = []
    for user in users:
        metadata = parse_jsonb_field(user.get("metadata"))
        formatted_users.append({
            "id": str(user["id"]),
            "fairyname": user["fairyname"],
            "email": user["email"],
            "phone": user["phone"],
            "is_builder": user["is_builder"],
            "is_admin": user["is_admin"],
            "is_active": user["is_active"],
            "dust_balance": user["dust_balance"],
            "created_at": user["created_at"].isoformat() if user["created_at"] else None,
            "updated_at": user["updated_at"].isoformat() if user["updated_at"] else None,
            "auth_provider": user["auth_provider"] or "email",
            "city": user["city"],
            "country": user["country"],
            "streak_days": user["streak_days"] or 0,
            "metadata": metadata,
        })

    return {
        "users": formatted_users,
        "total": total_count["total"],
        "pages": total_pages,
        "current_page": page
    }


# Additional JSON API endpoints for user management
@users_router.put("/{user_id}")
async def update_user_json(
    user_id: str,
    update_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update user data via JSON API"""
    # Verify user exists
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Build update query dynamically based on provided fields
    allowed_fields = ["is_active", "is_builder", "is_admin"]
    updates = []
    params = []
    param_count = 1

    for field, value in update_data.items():
        if field in allowed_fields:
            updates.append(f"{field} = ${param_count}")
            params.append(value)
            param_count += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Don't allow removing own admin status
    if (user_id == admin_user["user_id"] and 
        "is_admin" in update_data and 
        not update_data["is_admin"]):
        raise HTTPException(status_code=400, detail="Cannot remove your own admin privileges")

    # Execute update
    updates.append(f"updated_at = CURRENT_TIMESTAMP")
    params.append(user_id)
    
    await db.execute(
        f"UPDATE users SET {', '.join(updates)} WHERE id = ${param_count}",
        *params,
    )

    return {"success": True, "message": "User updated successfully"}


@users_router.delete("/{user_id}")
async def delete_user_json(
    user_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Delete user via JSON API"""
    # Verify user exists
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't allow deleting own account
    if user_id == admin_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Delete user (CASCADE will handle related records)
    await db.execute("DELETE FROM users WHERE id = $1", user_id)

    return {"success": True, "message": "User deleted successfully"}


@users_router.post("/{user_id}/grant-dust")
async def grant_dust(
    user_id: str,
    amount: int = Form(...),
    reason: str = Form(...),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
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
            user_id,
            amount,
            f"Admin grant: {reason}",
        )

        # Update user balance
        await conn.execute(
            "UPDATE users SET dust_balance = dust_balance + $1 WHERE id = $2", amount, user_id
        )

    return RedirectResponse(url=f"/admin/users?granted={amount}", status_code=302)


@users_router.post("/{user_id}/toggle-builder")
async def toggle_builder(
    user_id: str, admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
):
    # Verify user exists
    user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Toggle builder status
    new_builder_status = not user["is_builder"]
    await db.execute(
        "UPDATE users SET is_builder = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
        new_builder_status,
        user_id,
    )

    return RedirectResponse(url="/admin/users", status_code=302)


@users_router.post("/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: str, admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
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
        new_admin_status,
        user_id,
    )

    return RedirectResponse(url="/admin/users", status_code=302)
