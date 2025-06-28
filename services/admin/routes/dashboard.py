import asyncio

import httpx
from auth import get_current_admin_user
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from shared.database import Database, get_db

dashboard_router = APIRouter()


async def check_service_health() -> dict:
    """Check health status of all fairydust services"""
    services = {
        "Identity": "https://fairydust-identity-production.up.railway.app/health",
        "Ledger": "https://fairydust-ledger-production.up.railway.app/health",
        "Apps": "https://fairydust-apps-production.up.railway.app/health",
        "Content": "https://fairydust-content-production.up.railway.app/health",
        "Admin": "https://fairydust-admin-production.up.railway.app/health",
        "Builder": "https://fairydust-builder-production.up.railway.app/health",
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


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    # Get dashboard stats and health status concurrently
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

    # Check service health
    health_status = await check_service_health()

    return HTMLResponse(
        f"""
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
            .badge-sm {{ font-size: 0.75em; }}
            .service-status {{ font-size: 0.9em; }}
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
                            <a href="/admin/llm" class="btn btn-warning">LLM Management</a>
                        </div>
                    </div>
                </div>

                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">System Status</div>
                        <div class="card-body">
                            {"<span class='badge bg-success'><i class='fas fa-check-circle'></i> All Services Online</span>" if health_status["all_healthy"] else f"<span class='badge bg-{'warning' if health_status['healthy_count'] > 0 else 'danger'}'><i class='fas fa-{'exclamation-triangle' if health_status['healthy_count'] > 0 else 'times-circle'}'></i> {health_status['healthy_count']}/{health_status['total_count']} Services Online</span>"}
                            <div class="mt-2 service-status">
                                {"".join([f"<div class='d-flex justify-content-between align-items-center py-1'><small>{name}</small><span class='badge bg-{'success' if status['healthy'] else 'danger'} badge-sm'>{status['status']}</span></div>" for name, status in health_status["services"].items()])}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {f'<div class="alert alert-warning"><strong>Action Required:</strong> {pending_apps["count"]} apps pending approval. <a href="/admin/apps?status=pending">Review now</a></div>' if pending_apps["count"] > 0 else ''}
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    )
