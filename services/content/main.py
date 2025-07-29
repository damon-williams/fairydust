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

from activity_routes import router as activity_router
from character_routes import router as character_router
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fortune_routes import router as fortune_router
from image_routes import image_router
from inspire_routes import router as inspire_router
from recipe_routes import router as recipe_router
from restaurant_routes import router as restaurant_router
from routes import content_router
from story_routes import router as story_router
from wyr_routes import router as wyr_router

# Import modules with minimal logging
from shared.database import close_db, init_db
from shared.redis_client import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and Redis
    await init_db()
    await init_redis()
    logger.info("Content service started successfully")
    yield
    # Cleanup
    logger.info("Shutting down content service...")
    await close_db()
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title="fairydust Content Service",
    description="User-generated content storage and management for fairydust apps",
    version="1.0.0",
    lifespan=lifespan,
)


# Custom exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.error(f"Validation error on {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "details": exc.errors(),
            "message": "Request body validation failed. Check required fields and data types.",
        },
    )


# Add centralized middleware first (executed last)
from shared.middleware import add_middleware_to_app

# Content service specific endpoint limits
endpoint_limits = {
    "/recipes": 10 * 1024 * 1024,  # 10MB for recipe content
    "/content/stories/generate": 50 * 1024,  # 50KB for story generation requests
    "/content/stories": 1 * 1024 * 1024,  # 1MB for story content
    "/restaurant": 100 * 1024,  # 100KB for restaurant requests
    "/activity/search": 50 * 1024,  # 50KB for activity search requests
    "/apps/inspire/generate": 50 * 1024,  # 50KB for inspire generation requests
    "/apps/recipe/generate": 50 * 1024,  # 50KB for recipe generation requests
    "/apps/story/generate": 50 * 1024,  # 50KB for story generation requests
    "/apps/fortune-teller/generate": 50 * 1024,  # 50KB for fortune generation requests
    "/users/*/characters": 10 * 1024,  # 10KB for character management requests
    "/apps/would-you-rather/*": 20 * 1024,  # 20KB for would-you-rather requests
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
app.include_router(restaurant_router, prefix="/restaurant", tags=["restaurants"])
app.include_router(activity_router, tags=["activities"])
app.include_router(inspire_router, tags=["inspire"])
app.include_router(recipe_router, tags=["recipes-new"])
app.include_router(fortune_router, tags=["fortune-teller"])
app.include_router(character_router, tags=["characters"])
app.include_router(wyr_router, tags=["would-you-rather"])
app.include_router(image_router, tags=["images"])


@app.get("/")
async def root():
    return {"message": "fairydust Content Service is running", "version": "1.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "content"}


# Remove test endpoints - use only in development


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8006)),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
        log_level="info",
    )
