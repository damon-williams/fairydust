import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from shared.database import close_db, init_db
from shared.redis_client import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting admin service initialization...")

        # Allow schema init for admin service to ensure system_config table exists
        # since admin service needs access to system configuration
        os.environ.setdefault("SKIP_SCHEMA_INIT", "false")

        await init_db()
        logger.info("Database initialized successfully")

        await init_redis()
        logger.info("Redis initialized successfully")

        logger.info("Admin service startup completed")
        yield

    except Exception as e:
        logger.error(f"Admin service startup failed: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down admin service...")
        await close_db()
        await close_redis()
        logger.info("Admin service shutdown completed")


app = FastAPI(
    title="fairydust Admin Portal",
    version="2.18.0",
    description="Admin portal for fairydust platform with system configuration management",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add validation error handler for better debugging
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import logging

    logger = logging.getLogger(__name__)

    # Log detailed validation error information
    logger.error(f"Validation error on {request.method} {request.url}")
    logger.error(f"Validation errors: {exc.errors()}")

    # Try to log the request body if possible
    try:
        body = await request.body()
        if body:
            import json

            try:
                body_json = json.loads(body)
                logger.error(f"Request body: {body_json}")
            except:
                logger.error(f"Request body (raw): {body.decode()}")
    except Exception as e:
        logger.warning(f"Could not read request body: {e}")

    # Return detailed error response
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": "See server logs for request body details"},
    )


from routes import (
    apps_router,
    auth_router,
    dashboard_router,
    llm_router,
    referrals_router,
    system_router,
    users_router,
)
from routes.activity import activity_router
from routes.ai_analytics import ai_router
from routes.global_config import router as global_config_router
from routes.model_configs import model_configs_router
from routes.payments import payments_router
from routes.pricing import pricing_router
from routes.terms import terms_router

# Include all route modules FIRST
app.include_router(auth_router, prefix="/admin")
app.include_router(dashboard_router, prefix="/admin")
app.include_router(users_router, prefix="/admin/users")
app.include_router(apps_router, prefix="/admin/apps")
app.include_router(llm_router, prefix="/admin/llm")
app.include_router(ai_router, prefix="/admin/ai")
app.include_router(pricing_router, prefix="/admin/pricing")
app.include_router(referrals_router, prefix="/admin/referrals")
app.include_router(activity_router, prefix="/admin/activity")
app.include_router(payments_router, prefix="/admin/payments")
app.include_router(terms_router, prefix="/admin/terms")
app.include_router(system_router, prefix="/admin/system")
app.include_router(model_configs_router, prefix="/admin/model-configs")
app.include_router(global_config_router, prefix="/api")  # Global API endpoint

# Dynamic asset serving for any file with cache-busting
static_dir = Path(__file__).parent / "static"


@app.get("/vite.svg")
async def serve_vite_svg():
    """Serve vite.svg"""
    return FileResponse(str(static_dir / "vite.svg"))


@app.get("/assets/{filename}")
async def serve_assets(filename: str):
    """Serve any asset file with cache-busting headers and proper CORS"""
    asset_path = static_dir / "assets" / filename
    if asset_path.exists() and asset_path.is_file():
        # Determine content type based on file extension
        content_type = "application/octet-stream"
        if filename.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif filename.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif filename.endswith(".svg"):
            content_type = "image/svg+xml"
        elif filename.endswith(".png"):
            content_type = "image/png"
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            content_type = "image/jpeg"

        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "X-Content-Type-Options": "nosniff",
        }
        return FileResponse(str(asset_path), media_type=content_type, headers=headers)

    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Asset not found")


@app.get("/")
async def root():
    """Serve React app with CSP headers"""
    static_dir = Path(__file__).parent / "static"
    headers = {
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://fairydust-apps-staging.up.railway.app https://fairydust-apps-production.up.railway.app",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }
    return FileResponse(str(static_dir / "index.html"), headers=headers)


# Catch-all route for React app - MUST BE LAST
@app.get("/{path:path}")
async def serve_react_app(path: str):
    """Serve React app for all unmatched routes"""
    # Don't serve React app for assets or API routes
    if path.startswith("assets/") or path.startswith("vite.svg"):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Asset not found")

    # Only serve React app for admin routes and root
    if (
        not path.startswith("admin/")
        or path.startswith("admin/dashboard")
        or path.startswith("admin/users")
        or path.startswith("admin/apps")
        or path.startswith("admin/llm")
        or path.startswith("admin/ai-analytics")
        or path.startswith("admin/referrals")
        or path.startswith("admin/activity")
        or path.startswith("admin/deletion-logs")
        or path.startswith("admin/terms")
        or path.startswith("admin/system")
        or path.startswith("admin/settings")
    ):
        static_dir = Path(__file__).parent / "static"
        headers = {
            "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://fairydust-apps-staging.up.railway.app https://fairydust-apps-production.up.railway.app",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        }
        return FileResponse(str(static_dir / "index.html"), headers=headers)

    # Let FastAPI handle 404 for unknown API routes
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Not found")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8003))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
