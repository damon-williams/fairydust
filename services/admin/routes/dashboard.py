import asyncio
import os

import httpx
from auth import get_current_admin_user
from fastapi import APIRouter, Depends

from shared.database import Database, get_db

dashboard_router = APIRouter()


async def check_service_health() -> dict:
    """Check health status of all fairydust services"""
    # Environment-based service URLs
    environment = os.getenv("ENVIRONMENT", "production")
    env_suffix = "staging" if environment == "staging" else "production"

    services = {
        "Identity": f"https://fairydust-identity-{env_suffix}.up.railway.app/health",
        "Ledger": f"https://fairydust-ledger-{env_suffix}.up.railway.app/health",
        "Apps": f"https://fairydust-apps-{env_suffix}.up.railway.app/health",
        "Content": f"https://fairydust-content-{env_suffix}.up.railway.app/health",
        "Admin": f"https://fairydust-admin-{env_suffix}.up.railway.app/health",
    }

    async def check_single_service(name: str, url: str) -> tuple[str, bool, str]:
        """Check health of a single service"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return name, True, "OK"
                else:
                    return name, False, f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            return name, False, "Timeout"
        except httpx.ConnectError:
            return name, False, "Connection Error"
        except Exception as e:
            return name, False, f"Error: {str(e)[:30]}"

    # Check all services concurrently
    tasks = [check_single_service(name, url) for name, url in services.items()]
    results = await asyncio.gather(*tasks)

    # Format results
    service_status = {}
    healthy_count = 0

    for name, is_healthy, status in results:
        service_status[name] = {"healthy": is_healthy, "status": status}
        if is_healthy:
            healthy_count += 1

    return {
        "services": service_status,
        "healthy_count": healthy_count,
        "total_count": len(services),
        "all_healthy": healthy_count == len(services),
    }


@dashboard_router.get("/dashboard/stats")
async def get_dashboard_stats(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get dashboard statistics for React app"""
    total_users = await db.fetch_one("SELECT COUNT(*) as count FROM users WHERE is_active = true")
    total_apps = await db.fetch_one("SELECT COUNT(*) as count FROM apps")
    # Removed pending_apps query - auto-approval workflow
    total_dust_issued = await db.fetch_one(
        "SELECT COALESCE(SUM(amount), 0) as total FROM dust_transactions WHERE type = 'grant'"
    )
    active_users_today = await db.fetch_one(
        "SELECT COUNT(*) as count FROM users WHERE is_active = true AND DATE(last_login_date) = CURRENT_DATE"
    )
    active_users_week = await db.fetch_one(
        "SELECT COUNT(*) as count FROM users WHERE is_active = true AND last_login_date >= CURRENT_DATE - INTERVAL '7 days'"
    )
    new_users_week = await db.fetch_one(
        "SELECT COUNT(*) as count FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'"
    )
    total_dust_consumed = await db.fetch_one(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM dust_transactions WHERE type = 'consume'"
    )
    dust_consumed_today = await db.fetch_one(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM dust_transactions WHERE type = 'consume' AND DATE(created_at) = CURRENT_DATE"
    )
    dust_consumed_week = await db.fetch_one(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM dust_transactions WHERE type = 'consume' AND created_at >= CURRENT_DATE - INTERVAL '7 days'"
    )
    total_transactions = await db.fetch_one("SELECT COUNT(*) as count FROM dust_transactions")
    total_llm_usage = await db.fetch_one("SELECT COUNT(*) as count FROM llm_usage_logs")

    return {
        "total_users": total_users["count"],
        "total_apps": total_apps["count"],
        # Removed pending_apps - auto-approval workflow
        "total_dust_issued": total_dust_issued["total"],
        "active_users_today": active_users_today["count"],
        "active_users_week": active_users_week["count"],
        "new_users_week": new_users_week["count"],
        "total_dust_consumed": total_dust_consumed["total"],
        "dust_consumed_today": dust_consumed_today["total"],
        "dust_consumed_week": dust_consumed_week["total"],
        "total_transactions": total_transactions["count"],
        "total_llm_usage": total_llm_usage["count"],
    }


@dashboard_router.get("/dashboard/health")
async def get_system_health(admin_user: dict = Depends(get_current_admin_user)):
    """Get system health status for React app"""
    health_status = await check_service_health()

    # Convert to format expected by React app
    services = {}
    for name, status in health_status["services"].items():
        key = name.lower()
        if status["healthy"]:
            services[key] = "online"
        else:
            services[key] = "offline"

    return services


@dashboard_router.get("/dashboard/recent-users")
async def get_recent_users(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get recent users by app usage (not account creation) for React app"""
    recent_users = await db.fetch_all(
        """SELECT DISTINCT u.id, u.fairyname, u.email, u.phone, u.is_builder, u.is_admin, u.is_active,
                  u.dust_balance, u.auth_provider, u.total_logins, u.created_at, u.updated_at,
                  MAX(dt.created_at) as last_activity_at
           FROM users u
           LEFT JOIN dust_transactions dt ON u.id = dt.user_id AND dt.type = 'consume'
           WHERE u.is_active = true
           GROUP BY u.id, u.fairyname, u.email, u.phone, u.is_builder, u.is_admin, u.is_active,
                    u.dust_balance, u.auth_provider, u.total_logins, u.created_at, u.updated_at
           ORDER BY last_activity_at DESC NULLS LAST, u.created_at DESC
           LIMIT 10"""
    )

    return [dict(user) for user in recent_users]


@dashboard_router.get("/dashboard/recent-apps")
async def get_recent_apps(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get recent apps for React app"""
    recent_apps = await db.fetch_all(
        """
        SELECT a.id, a.name, a.slug, a.description, a.status, a.builder_id,
               u.fairyname as builder_name, a.category, a.icon_url,
               a.created_at, a.updated_at
        FROM apps a
        JOIN users u ON a.builder_id = u.id
        ORDER BY a.created_at DESC
        LIMIT 10
        """
    )

    return [dict(app) for app in recent_apps]


@dashboard_router.get("/dashboard/recent-activity")
async def get_recent_activity(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get recent DUST activity (both consumption and grants) for React app"""
    recent_activity = await db.fetch_all(
        """
        SELECT
            dt.id,
            dt.amount,
            dt.type,
            dt.description,
            dt.created_at,
            u.fairyname,
            u.first_name,
            u.id as user_id
        FROM dust_transactions dt
        JOIN users u ON dt.user_id = u.id
        ORDER BY dt.created_at DESC
        LIMIT 10
        """
    )

    return [dict(activity) for activity in recent_activity]
