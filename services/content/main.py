# services/content/main.py
import logging
import os
import sys

# Force unbuffered output for Railway
os.environ["PYTHONUNBUFFERED"] = "1"

# Minimal startup logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

from character_routes import router as character_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fortune_routes import router as fortune_router
from image_routes import image_router
from inspire_routes import router as inspire_router
from recipe_routes import router as recipe_router
from routes import content_router
from story_routes import router as story_router
from twenty_questions_routes import router as twenty_questions_router
from video_background_processor import video_background_processor
from video_routes import video_router
from wyr_routes import router as wyr_router

# Import modules with minimal logging
from shared.database import close_db, init_db
from shared.redis_client import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Force schema initialization for content service to ensure retry columns exist
    os.environ.setdefault("SKIP_SCHEMA_INIT", "false")

    # Initialize database and Redis
    await init_db()

    # EMERGENCY: Add retry columns directly if they don't exist
    # This bypasses any shared/database.py issues
    try:
        from shared.database import get_db

        db = await get_db()

        logger.info("🔧 EMERGENCY: Adding retry columns directly...")

        # Add columns one by one
        try:
            await db.execute_schema(
                "ALTER TABLE story_images ADD COLUMN IF NOT EXISTS attempt_number INTEGER DEFAULT 1"
            )
            logger.info("✅ Added attempt_number column")
        except Exception as e:
            logger.info(f"📝 attempt_number: {e}")

        try:
            await db.execute_schema(
                "ALTER TABLE story_images ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3"
            )
            logger.info("✅ Added max_attempts column")
        except Exception as e:
            logger.info(f"📝 max_attempts: {e}")

        try:
            await db.execute_schema(
                "ALTER TABLE story_images ADD COLUMN IF NOT EXISTS retry_reason TEXT DEFAULT NULL"
            )
            logger.info("✅ Added retry_reason column")
        except Exception as e:
            logger.info(f"📝 retry_reason: {e}")

        logger.info("🔧 EMERGENCY: Retry columns setup complete")

    except Exception as e:
        logger.error(f"❌ EMERGENCY: Failed to add retry columns: {e}")

    await init_redis()

    # Start video background processor
    import asyncio

    asyncio.create_task(video_background_processor.start())

    logger.info("Content service started successfully")
    yield

    # Cleanup
    logger.info("Shutting down content service...")
    await video_background_processor.stop()
    await close_db()
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title="fairydust Content Service",
    description="User-generated content storage and management for fairydust apps",
    version="1.0.0",
    lifespan=lifespan,
)


# Exception handlers are now handled by shared middleware


# Add centralized middleware first (executed last)
from shared.middleware import add_middleware_to_app

# Content service specific endpoint limits
endpoint_limits = {
    "/recipes": 10 * 1024 * 1024,  # 10MB for recipe content
    "/content/stories/generate": 50 * 1024,  # 50KB for story generation requests
    "/content/stories": 1 * 1024 * 1024,  # 1MB for story content
    "/apps/inspire/generate": 50 * 1024,  # 50KB for inspire generation requests
    "/apps/recipe/generate": 50 * 1024,  # 50KB for recipe generation requests
    "/apps/story/generate": 50 * 1024,  # 50KB for story generation requests
    "/apps/fortune-teller/generate": 50 * 1024,  # 50KB for fortune generation requests
    "/users/*/characters": 10 * 1024,  # 10KB for character management requests
    "/apps/would-you-rather/*": 20 * 1024,  # 20KB for would-you-rather requests
    "/twenty-questions/*": 20 * 1024,  # 20KB for 20 questions game requests
    "/images/generate": 100 * 1024,  # 100KB for image generation requests
    "/images/*/regenerate": 100 * 1024,  # 100KB for image regeneration requests
}

add_middleware_to_app(
    app=app,
    service_name="content",
    max_request_size=15 * 1024 * 1024,  # 15MB default for content service
    endpoint_limits=endpoint_limits,
    log_requests=True,
)

# CORS middleware (executed first)
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Enhanced request logging with detailed error information
@app.middleware("http")
async def log_requests(request, call_next):
    import time
    import traceback

    start_time = time.time()

    try:
        response = await call_next(request)

        # Log errors with detailed information
        if response.status_code >= 400:
            duration_ms = int((time.time() - start_time) * 1000)

            # Get client info
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Log basic request info
            logger.error(
                f"🔥 {request.method} {request.url.path} - {response.status_code} "
                f"({duration_ms}ms) from {client_ip}"
            )

            # Log query parameters if present
            if request.query_params:
                logger.error(f"   Query params: {dict(request.query_params)}")

            # Log headers (excluding sensitive ones)
            safe_headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in ["authorization", "cookie", "x-api-key"]
            }
            if safe_headers:
                logger.error(f"   Headers: {safe_headers}")

            # For 500 errors, try to read the response body for additional context
            if response.status_code >= 500:
                logger.error(f"   User-Agent: {user_agent}")

        return response

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        client_ip = request.client.host if request.client else "unknown"

        logger.error(
            f"💥 UNHANDLED EXCEPTION {request.method} {request.url.path} "
            f"({duration_ms}ms) from {client_ip}: {str(e)}"
        )
        logger.error(f"   Exception type: {type(e).__name__}")
        logger.error(f"   Traceback: {traceback.format_exc()}")

        # Re-raise the exception
        raise


# Include routers
app.include_router(content_router, prefix="/recipes", tags=["recipes"])
app.include_router(story_router, tags=["stories"])
app.include_router(inspire_router, tags=["inspire"])
app.include_router(recipe_router, tags=["recipes-new"])
app.include_router(fortune_router, tags=["fortune-teller"])
app.include_router(character_router, tags=["characters"])
app.include_router(wyr_router, tags=["would-you-rather"])
app.include_router(twenty_questions_router, prefix="/twenty-questions", tags=["twenty-questions"])
app.include_router(image_router, tags=["images"])
app.include_router(video_router, prefix="/videos", tags=["videos"])


@app.get("/")
async def root():
    return {"message": "fairydust Content Service is running", "version": "1.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "content"}


# Remove test endpoints - use only in development


if __name__ == "__main__":
    import uvicorn

    # Configure for longer video generation requests
    timeout_seconds = int(os.getenv("REQUEST_TIMEOUT", "600"))  # Default 10 minutes

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8006)),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
        log_level="info",
        timeout_keep_alive=timeout_seconds,
        timeout_graceful_shutdown=timeout_seconds,
    )
