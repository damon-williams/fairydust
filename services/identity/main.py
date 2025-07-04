import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

# Import our routes and dependencies
from routes import auth_router, user_router

from shared.database import close_db, init_db
from shared.redis_client import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(
        "🚀 IDENTITY SERVICE: Starting with debugging logs for is_onboarding_completed (v2.1.12)",
        flush=True,
    )
    await init_db()
    await init_redis()
    print("✅ IDENTITY SERVICE: Startup complete - ready to serve requests", flush=True)
    yield
    # Shutdown
    await close_db()
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title="fairydust Identity Service",
    version="1.0.0",
    description="Authentication and identity management for fairydust platform",
    lifespan=lifespan,
)

# Configure CORS
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

# Identity service specific endpoint limits
endpoint_limits = {
    "/auth/otp/request": 1024,  # 1KB limit for OTP requests
    "/auth/otp/verify": 1024,  # 1KB limit for OTP verification
    "/users/profile": 50 * 1024,  # 50KB for profile data
    "/users/people": 10 * 1024,  # 10KB for people data
}

add_middleware_to_app(
    app=app,
    service_name="identity",
    max_request_size=1 * 1024 * 1024,  # 1MB default for identity service
    endpoint_limits=endpoint_limits,
    log_requests=True,
)


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "identity", "version": "1.0.0"}


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["authentication"])
app.include_router(user_router, prefix="/users", tags=["users"])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
