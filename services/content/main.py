# services/content/main.py
import logging
import os
import sys
import time

# Force unbuffered output for Railway
os.environ["PYTHONUNBUFFERED"] = "1"

print("🚨 STARTUP: Starting content service import phase...", flush=True)
print("🚨 STARTUP: Basic imports successful", flush=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

print("🚨 STARTUP: FastAPI imports successful", flush=True)

try:
    from shared.database import close_db, init_db

    print("🚨 STARTUP: Database imports successful", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Database import failed: {e}", flush=True)
    raise

try:
    from shared.redis_client import close_redis, init_redis

    print("🚨 STARTUP: Redis imports successful", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Redis import failed: {e}", flush=True)
    raise

try:
    from routes import content_router

    print("🚨 STARTUP: Content routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Content routes import failed: {e}", flush=True)
    raise

try:
    from story_routes import router as story_router

    print("🚨 STARTUP: Story routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Story routes import failed: {e}", flush=True)
    raise

try:
    from restaurant_routes import router as restaurant_router

    print("🚨 STARTUP: Restaurant routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Restaurant routes import failed: {e}", flush=True)
    raise

try:
    from activity_routes import router as activity_router

    print("🚨 STARTUP: Activity routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Activity routes import failed: {e}", flush=True)
    raise

try:
    from inspire_routes import router as inspire_router

    print("🚨 STARTUP: Inspire routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Inspire routes import failed: {e}", flush=True)
    raise

try:
    from recipe_routes import router as recipe_router

    print("🚨 STARTUP: Recipe routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Recipe routes import failed: {e}", flush=True)
    raise

try:
    from fortune_routes import router as fortune_router

    print("🚨 STARTUP: Fortune routes imported successfully", flush=True)
except Exception as e:
    print(f"🚨 STARTUP: ❌ Fortune routes import failed: {e}", flush=True)
    raise

print("🚨 STARTUP: All imports completed successfully", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and Redis
    print("🚨 CONTENT_SERVICE: Starting content service initialization...", flush=True)
    await init_db()
    print("🚨 CONTENT_SERVICE: Database initialized", flush=True)
    await init_redis()
    print("🚨 CONTENT_SERVICE: Redis initialized", flush=True)
    print("🚨 CONTENT_SERVICE: Content service started successfully", flush=True)
    logger.info("Content service started successfully")
    yield
    # Cleanup
    print("🚨 CONTENT_SERVICE: Shutting down content service...", flush=True)
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
    """Handle validation errors and log request body for debugging"""
    try:
        request_body = await request.body()
        print(f"❌ VALIDATION_ERROR: Request body: {request_body.decode('utf-8')}", flush=True)
    except Exception as e:
        print(f"❌ VALIDATION_ERROR: Could not read request body: {e}", flush=True)

    print(f"❌ VALIDATION_ERROR: {exc.errors()}", flush=True)
    print(f"❌ VALIDATION_ERROR: URL: {request.url}", flush=True)

    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "details": exc.errors(),
            "message": "Request body validation failed. Check required fields and data types.",
        },
    )


# CORS middleware
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add centralized middleware
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
}

add_middleware_to_app(
    app=app,
    service_name="content",
    max_request_size=15 * 1024 * 1024,  # 15MB default for content service
    endpoint_limits=endpoint_limits,
    log_requests=True,
)


# Add custom middleware to log ALL requests
@app.middleware("http")
async def log_all_requests(request, call_next):
    print(
        f"🔍 REQUEST_DEBUG: {request.method} {request.url.path} - Headers: {dict(request.headers)}",
        flush=True,
    )
    print(f"🔍 REQUEST_DEBUG: Query params: {dict(request.query_params)}", flush=True)
    response = await call_next(request)
    print(f"🔍 REQUEST_DEBUG: Response status: {response.status_code}", flush=True)
    return response


# Include routers
print("🚨 CONTENT_SERVICE: Including routers...", flush=True)
app.include_router(content_router, prefix="/recipes", tags=["recipes"])
app.include_router(story_router, tags=["stories"])
app.include_router(restaurant_router, prefix="/restaurant", tags=["restaurants"])
app.include_router(activity_router, tags=["activities"])
app.include_router(inspire_router, tags=["inspire"])
app.include_router(recipe_router, tags=["recipes-new"])
app.include_router(fortune_router, tags=["fortune-teller"])
print("🚨 CONTENT_SERVICE: All routers included successfully", flush=True)
print(
    "🚨 CONTENT_SERVICE: Router prefixes - recipes: /recipes, stories: /, restaurants: /restaurant, activities: /, inspire: /, recipe-new: /, fortune: /",
    flush=True,
)
print("🚨 CONTENT_SERVICE: Expected story URL: /apps/story/generate", flush=True)
print("🚨 CONTENT_SERVICE: Expected restaurant URL: /restaurant/generate", flush=True)
print("🚨 CONTENT_SERVICE: Expected activity URL: /activity/search", flush=True)
print("🚨 CONTENT_SERVICE: Expected fortune URL: /apps/fortune-teller/generate", flush=True)


@app.get("/")
async def root():
    print("🚨 CONTENT_SERVICE: Root endpoint hit", flush=True)
    return {"message": "fairydust Content Service is running", "version": "1.1.0"}


@app.get("/health")
async def health():
    print("🚨 CONTENT_SERVICE: Health endpoint hit", flush=True)
    return {"status": "healthy", "service": "content"}


@app.get("/test-restaurant")
async def test_restaurant():
    print("🚨 CONTENT_SERVICE: Test restaurant endpoint hit", flush=True)
    return {"message": "Restaurant router is working", "timestamp": time.time()}


@app.get("/test-logging")
async def test_logging():
    """Test endpoint to debug Railway logging issues"""
    import datetime

    # Try multiple logging methods
    msg = f"Test log at {datetime.datetime.utcnow()}"

    # Method 1: print to stdout with flush
    print(f"PRINT: {msg}", flush=True)

    # Method 2: print to stderr with flush
    print(f"STDERR: {msg}", file=sys.stderr, flush=True)

    # Method 3: logging module
    logger.info(f"LOGGER: {msg}")

    # Method 4: direct stdout write with flush
    sys.stdout.write(f"STDOUT: {msg}\n")
    sys.stdout.flush()

    # Method 5: Force all streams to flush
    sys.stdout.flush()
    sys.stderr.flush()

    return {
        "message": "Logged using 4 different methods with explicit flushing",
        "timestamp": time.time(),
        "methods": ["print+flush", "stderr+flush", "logger", "stdout.write+flush", "forced_flush"],
    }


@app.get("/test-googlemaps")
async def test_googlemaps():
    print("🚨 CONTENT_SERVICE: Test googlemaps endpoint hit", flush=True)
    try:
        import googlemaps

        return {
            "status": "success",
            "message": "googlemaps package available",
            "version": getattr(googlemaps, "__version__", "unknown"),
            "timestamp": time.time(),
        }
    except ImportError as e:
        return {
            "status": "error",
            "message": f"googlemaps package not available: {e}",
            "timestamp": time.time(),
        }


if __name__ == "__main__":
    print("🚨 CONTENT_SERVICE: Starting uvicorn server...", flush=True)
    print(f"🚨 CONTENT_SERVICE: Environment: {os.getenv('ENVIRONMENT', 'development')}", flush=True)
    print(f"🚨 CONTENT_SERVICE: Port: {os.getenv('PORT', 8006)}", flush=True)

    try:
        import uvicorn

        print("🚨 CONTENT_SERVICE: ✅ uvicorn imported successfully", flush=True)

        # Configure uvicorn logging
        log_config = uvicorn.config.LOGGING_CONFIG
        log_config["formatters"]["default"][
            "fmt"
        ] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        log_config["formatters"]["access"][
            "fmt"
        ] = '%(asctime)s - %(name)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'

        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8006)),
            reload=os.getenv("ENVIRONMENT", "development") == "development",
            log_config=log_config,
            log_level="info",
            access_log=True,
        )
    except Exception as e:
        print(f"🚨 CONTENT_SERVICE: ❌ Failed to start uvicorn: {e}", flush=True)
        logger.error(f"Failed to start uvicorn: {e}", exc_info=True)
        import traceback

        traceback.print_exc()
        raise
