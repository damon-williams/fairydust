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
    """Delete user via JSON API with audit logging"""
    import json
    from datetime import datetime
    from uuid import uuid4

    # Verify user exists
    user_data = await db.fetch_one(
        """SELECT fairyname, email, created_at, dust_balance,
                  avatar_url, avatar_uploaded_at, avatar_size_bytes
           FROM users WHERE id = $1""",
        user_id,
    )
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't allow deleting own account
    if user_id == admin_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    try:
        # Gather data summary for audit log
        stats_queries = [
            ("recipes_created", "SELECT COUNT(*) as count FROM user_recipes WHERE user_id = $1"),
            ("stories_created", "SELECT COUNT(*) as count FROM user_stories WHERE user_id = $1"),
            ("images_generated", "SELECT COUNT(*) as count FROM user_images WHERE user_id = $1"),
            (
                "people_in_life",
                "SELECT COUNT(*) as count FROM people_in_my_life WHERE user_id = $1",
            ),
            (
                "total_transactions",
                "SELECT COUNT(*) as count FROM dust_transactions WHERE user_id = $1",
            ),
            ("referrals_made", "SELECT COUNT(*) as count FROM referral_codes WHERE user_id = $1"),
        ]

        data_summary = {
            "dust_balance": user_data["dust_balance"],
            "account_age_days": (
                datetime.utcnow().replace(tzinfo=None)
                - user_data["created_at"].replace(tzinfo=None)
            ).days
            if user_data["created_at"]
            else 0,
            "has_avatar": bool(user_data["avatar_url"]),
            "admin_deletion_reason": "admin_action",
            "deleted_by_admin": admin_user.get("fairyname", "unknown_admin"),
        }

        # Get counts for data summary
        for stat_name, query in stats_queries:
            try:
                result = await db.fetch_one(query, user_id)
                data_summary[stat_name] = result["count"] if result else 0
            except Exception:
                data_summary[stat_name] = 0

        # Create deletion log entry
        deletion_id = str(uuid4())
        await db.execute(
            """INSERT INTO account_deletion_logs
               (id, user_id, fairyname, email, deletion_reason, deletion_feedback,
                deleted_by, deleted_by_user_id, user_created_at, data_summary, deletion_requested_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)""",
            deletion_id,
            user_id,
            user_data["fairyname"],
            user_data["email"],
            "other",  # Admin deletions use "other" as reason
            f"Admin deletion by {admin_user.get('fairyname', 'unknown')}",
            "admin",
            admin_user["user_id"],
            user_data["created_at"],
            json.dumps(data_summary),
        )

        # Delete storage assets (avatars, people photos, generated images)
        # Import here to avoid circular import issues
        from shared.storage_service import delete_user_assets

        storage_deletion_summary = await delete_user_assets(user_id)

        # Delete user record (CASCADE will handle all related data)
        await db.execute("DELETE FROM users WHERE id = $1", user_id)

        # Update deletion log with completion
        await db.execute(
            """UPDATE account_deletion_logs
               SET deletion_completed_at = CURRENT_TIMESTAMP,
                   data_summary = data_summary || $2
               WHERE id = $1""",
            deletion_id,
            json.dumps({"storage_cleanup": storage_deletion_summary}),
        )

        return {
            "success": True,
            "message": "User deleted successfully",
            "deletion_id": deletion_id,
            "storage_cleanup": storage_deletion_summary,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"User deletion failed: {str(e)}")


@users_router.get("/deletion-logs")
async def get_deletion_logs(
    limit: int = 50,
    offset: int = 0,
    deleted_by: str = None,  # Filter by 'self' or 'admin'
    reason: str = None,  # Filter by deletion reason
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get account deletion logs for admin review"""

    # Build query conditions
    conditions = []
    params = []
    param_count = 1

    if deleted_by:
        conditions.append(f"deleted_by = ${param_count}")
        params.append(deleted_by)
        param_count += 1

    if reason:
        conditions.append(f"deletion_reason = ${param_count}")
        params.append(reason)
        param_count += 1

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM account_deletion_logs {where_clause}"
    total_result = await db.fetch_one(count_query, *params)
    total = total_result["total"] if total_result else 0

    # Get deletion logs with pagination
    logs_query = f"""
        SELECT id, user_id, fairyname, email, deletion_reason, deletion_feedback,
               deleted_by, deleted_by_user_id, user_created_at, deletion_requested_at,
               deletion_completed_at, data_summary
        FROM account_deletion_logs
        {where_clause}
        ORDER BY deletion_requested_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """
    params.extend([limit, offset])

    logs = await db.fetch_all(logs_query, *params)

    # Format response
    deletion_logs = []
    for log in logs:
        log_data = dict(log)
        # Parse JSON data_summary if it exists
        if log_data["data_summary"]:
            try:
                import json

                log_data["data_summary"] = json.loads(log_data["data_summary"])
            except:
                log_data["data_summary"] = {}

        deletion_logs.append(log_data)

    return {
        "deletion_logs": deletion_logs,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
        "filters": {"deleted_by": deleted_by, "reason": reason},
    }


@users_router.get("/deletion-logs/stats")
async def get_deletion_stats(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get deletion statistics for admin dashboard"""

    # Get deletion counts by reason
    reason_stats = await db.fetch_all(
        """
        SELECT deletion_reason, COUNT(*) as count
        FROM account_deletion_logs
        GROUP BY deletion_reason
        ORDER BY count DESC
    """
    )

    # Get deletion counts by type (self vs admin)
    type_stats = await db.fetch_all(
        """
        SELECT deleted_by, COUNT(*) as count
        FROM account_deletion_logs
        GROUP BY deleted_by
    """
    )

    # Get recent deletion trend (last 30 days)
    trend_stats = await db.fetch_all(
        """
        SELECT DATE(deletion_requested_at) as deletion_date, COUNT(*) as count
        FROM account_deletion_logs
        WHERE deletion_requested_at >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(deletion_requested_at)
        ORDER BY deletion_date DESC
        LIMIT 30
    """
    )

    # Get total counts
    total_deletions = await db.fetch_one(
        """
        SELECT COUNT(*) as total
        FROM account_deletion_logs
    """
    )

    return {
        "total_deletions": total_deletions["total"] if total_deletions else 0,
        "deletion_reasons": [dict(row) for row in reason_stats],
        "deletion_types": [dict(row) for row in type_stats],
        "recent_trend": [dict(row) for row in trend_stats],
    }


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
