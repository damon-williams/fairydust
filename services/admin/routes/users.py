from typing import Optional

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, HTTPException

from shared.database import Database, get_db

users_router = APIRouter()


# JSON API endpoint for React app
@users_router.get("/api")
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
               avatar_url, first_name, birth_date, last_login_date
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
        formatted_users.append(
            {
                "id": str(user["id"]),
                "fairyname": user["fairyname"],
                "email": user["email"],
                "phone": user["phone"],
                "avatar_url": user["avatar_url"],
                "is_builder": user["is_builder"],
                "is_admin": user["is_admin"],
                "is_active": user["is_active"],
                "first_name": user["first_name"],
                "birth_date": user["birth_date"].isoformat() if user["birth_date"] else None,
                "city": user["city"],
                "country": user["country"],
                "dust_balance": user["dust_balance"],
                "auth_provider": user["auth_provider"] or "email",
                "last_login_date": user["last_login_date"].isoformat()
                if user["last_login_date"]
                else None,
                "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                "updated_at": user["updated_at"].isoformat() if user["updated_at"] else None,
            }
        )

    return {
        "users": formatted_users,
        "total": total_count["total"],
        "pages": total_pages,
        "current_page": page,
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
    if (
        user_id == admin_user["user_id"]
        and "is_admin" in update_data
        and not update_data["is_admin"]
    ):
        raise HTTPException(status_code=400, detail="Cannot remove your own admin privileges")

    # Execute update
    updates.append("updated_at = CURRENT_TIMESTAMP")
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
async def grant_dust_api(
    user_id: str,
    grant_data: dict,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Grant DUST to user via JSON API"""
    amount = grant_data.get("amount")
    reason = grant_data.get("reason", "Admin grant")

    if not amount or amount <= 0:
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
            f"Admin grant by {admin_user['fairyname']}: {reason}",
        )

        # Update user balance
        await conn.execute(
            "UPDATE users SET dust_balance = dust_balance + $1 WHERE id = $2", amount, user_id
        )

    return {"success": True, "message": f"Granted {amount} DUST to user"}


@users_router.post("/{user_id}/toggle-builder")
async def toggle_builder_api(
    user_id: str, admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
):
    """Toggle builder status via JSON API"""
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

    return {"success": True, "is_builder": new_builder_status}


@users_router.post("/{user_id}/toggle-admin")
async def toggle_admin_api(
    user_id: str, admin_user: dict = Depends(get_current_admin_user), db: Database = Depends(get_db)
):
    """Toggle admin status via JSON API"""
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

    return {"success": True, "is_admin": new_admin_status}
