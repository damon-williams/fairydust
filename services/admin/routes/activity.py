from typing import Optional

from auth import get_current_admin_user
from fastapi import APIRouter, Depends, Query

from shared.database import Database, get_db

activity_router = APIRouter()


@activity_router.get("/api")
async def get_activity_json(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user_search: Optional[str] = Query(None),
    activity_type: Optional[str] = Query(None),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get DUST activity (both consumption and grants) as JSON for React app"""
    offset = (page - 1) * limit

    # Build query conditions - now include all activity types
    where_conditions = []  # Remove consumption-only filter
    params = []

    if user_search:
        where_conditions.append(
            "(u.fairyname ILIKE $%d OR u.first_name ILIKE $%d OR u.email ILIKE $%d)"
            % (len(params) + 1, len(params) + 1, len(params) + 1)
        )
        params.append(f"%{user_search}%")

    if activity_type and activity_type != "all":
        # Map activity types to transaction descriptions
        if activity_type == "grant":
            where_conditions.append("dt.type = $%d" % (len(params) + 1))
            params.append("grant")
        elif activity_type == "recipe":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%recipe%")
        elif activity_type == "story":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%story%")
        elif activity_type == "activity":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%activity%")
        elif activity_type == "restaurant":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%restaurant%")
        elif activity_type == "image":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%image%")
        elif activity_type == "video":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%video%")
        elif activity_type == "inspiration":
            where_conditions.append(
                "(dt.description ILIKE $%d OR dt.description ILIKE $%d)"
                % (len(params) + 1, len(params) + 2)
            )
            params.append("%inspiration%")
            params.append("%inspire%")
        elif activity_type == "fortune":
            where_conditions.append("dt.description ILIKE $%d" % (len(params) + 1))
            params.append("%fortune%")
        elif activity_type == "wyr":
            where_conditions.append(
                "(dt.description ILIKE $%d OR dt.description ILIKE $%d)"
                % (len(params) + 1, len(params) + 2)
            )
            params.append("%would you rather%")
            params.append("%wyr%")

    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # Get total count
    count_query = f"""
        SELECT COUNT(*) as total
        FROM dust_transactions dt
        JOIN users u ON dt.user_id = u.id
        {where_clause}
    """
    total_result = await db.fetch_one(count_query, *params)
    total_count = total_result["total"] if total_result else 0
    total_pages = (total_count + limit - 1) // limit

    # Get activity with pagination
    activity_query = f"""
        SELECT
            dt.id,
            dt.amount,
            dt.type,
            dt.description,
            dt.created_at,
            u.fairyname,
            u.first_name,
            u.id as user_id,
            u.avatar_url
        FROM dust_transactions dt
        JOIN users u ON dt.user_id = u.id
        {where_clause}
        ORDER BY dt.created_at DESC
        LIMIT {limit} OFFSET {offset}
    """

    activities = await db.fetch_all(activity_query, *params)

    # Format activities for JSON response
    formatted_activities = []
    for activity in activities:
        # Check if this is a grant first
        if activity["type"] == "grant" or activity["amount"] > 0:
            activity_type = "grant"
            icon = "💰"
        else:
            # Determine activity type from description for consumption
            description = activity["description"].lower()
            if "recipe" in description:
                activity_type = "recipe"
                icon = "🍳"
            elif "story" in description:
                activity_type = "story"
                icon = "📖"
            elif "activity" in description or "search" in description:
                activity_type = "activity"
                icon = "🎯"
            elif "restaurant" in description:
                activity_type = "restaurant"
                icon = "🍽️"
            elif "image" in description:
                activity_type = "image"
                icon = "🎨"
            elif "video" in description:
                activity_type = "video"
                icon = "🎬"
            elif "inspiration" in description or "inspire" in description:
                activity_type = "inspiration"
                icon = "✨"
            elif "fortune" in description:
                activity_type = "fortune"
                icon = "🔮"
            elif "would you rather" in description or "wyr" in description:
                activity_type = "wyr"
                icon = "🤔"
            else:
                activity_type = "other"
                icon = "💫"

        formatted_activities.append(
            {
                "id": str(activity["id"]),
                "amount": abs(activity["amount"]),  # Show as positive for display
                "type": activity["type"],
                "activity_type": activity_type,
                "icon": icon,
                "description": activity["description"],
                "created_at": activity["created_at"].isoformat()
                if activity["created_at"]
                else None,
                "user": {
                    "id": str(activity["user_id"]),
                    "fairyname": activity["fairyname"],
                    "first_name": activity["first_name"],
                    "avatar_url": activity["avatar_url"],
                },
            }
        )

    return {
        "activities": formatted_activities,
        "total": total_count,
        "pages": total_pages,
        "current_page": page,
        "has_more": page < total_pages,
    }
