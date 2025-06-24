# services/content/main.py
print("🚨 STARTUP: Starting content service import phase...")

import os
import time
print("🚨 STARTUP: Basic imports successful")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
print("🚨 STARTUP: FastAPI imports successful")

try:
    from shared.database import init_db, close_db
    print("🚨 STARTUP: Database imports successful")
except Exception as e:
    print(f"🚨 STARTUP: ❌ Database import failed: {e}")
    raise

try:
    from shared.redis_client import init_redis, close_redis
    print("🚨 STARTUP: Redis imports successful")
except Exception as e:
    print(f"🚨 STARTUP: ❌ Redis import failed: {e}")
    raise

try:
    from routes import content_router
    print("🚨 STARTUP: Content routes imported successfully")
except Exception as e:
    print(f"🚨 STARTUP: ❌ Content routes import failed: {e}")
    raise

try:
    from story_routes import router as story_router
    print("🚨 STARTUP: Story routes imported successfully")
except Exception as e:
    print(f"🚨 STARTUP: ❌ Story routes import failed: {e}")
    raise

try:
    from restaurant_routes import router as restaurant_router
    print("🚨 STARTUP: Restaurant routes imported successfully")
except Exception as e:
    print(f"🚨 STARTUP: ❌ Restaurant routes import failed: {e}")
    raise

print("🚨 STARTUP: All imports completed successfully")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and Redis
    print("🚨 CONTENT_SERVICE: Starting content service initialization...")
    await init_db()
    print("🚨 CONTENT_SERVICE: Database initialized")
    await init_redis()
    print("🚨 CONTENT_SERVICE: Redis initialized")
    print("🚨 CONTENT_SERVICE: Content service started successfully")
    yield
    # Cleanup
    print("🚨 CONTENT_SERVICE: Shutting down content service...")
    await close_db()
    await close_redis()

# Create FastAPI app
app = FastAPI(
    title="fairydust Content Service",
    description="User-generated content storage and management for fairydust apps",
    version="1.0.0",
    lifespan=lifespan
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
}

add_middleware_to_app(
    app=app,
    service_name="content",
    max_request_size=15 * 1024 * 1024,  # 15MB default for content service
    endpoint_limits=endpoint_limits,
    log_requests=True
)

# Include routers
print("🚨 CONTENT_SERVICE: Including routers...")
app.include_router(content_router, prefix="/recipes", tags=["recipes"])
app.include_router(story_router, prefix="/content", tags=["stories"])
app.include_router(restaurant_router, prefix="/restaurant", tags=["restaurants"])
print("🚨 CONTENT_SERVICE: All routers included successfully")

@app.get("/")
async def root():
    print("🚨 CONTENT_SERVICE: Root endpoint hit")
    return {"message": "fairydust Content Service is running", "version": "1.1.0"}

@app.get("/health")
async def health():
    print("🚨 CONTENT_SERVICE: Health endpoint hit")
    return {"status": "healthy", "service": "content"}

@app.get("/test-restaurant")
async def test_restaurant():
    print("🚨 CONTENT_SERVICE: Test restaurant endpoint hit")
    return {"message": "Restaurant router is working", "timestamp": time.time()}

@app.get("/test-googlemaps")
async def test_googlemaps():
    print("🚨 CONTENT_SERVICE: Test googlemaps endpoint hit")
    try:
        import googlemaps
        return {
            "status": "success", 
            "message": "googlemaps package available",
            "version": getattr(googlemaps, '__version__', 'unknown'),
            "timestamp": time.time()
        }
    except ImportError as e:
        return {
            "status": "error",
            "message": f"googlemaps package not available: {e}",
            "timestamp": time.time()
        }

if __name__ == "__main__":
    print("🚨 CONTENT_SERVICE: Starting uvicorn server...")
    try:
        import uvicorn
        print("🚨 CONTENT_SERVICE: ✅ uvicorn imported successfully")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8006)),
            reload=os.getenv("ENVIRONMENT", "development") == "development"
        )
    except Exception as e:
        print(f"🚨 CONTENT_SERVICE: ❌ Failed to start uvicorn: {e}")
        import traceback
        traceback.print_exc()
        raise