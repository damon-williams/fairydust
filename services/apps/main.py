# services/apps/main.py
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routes import (
    admin_router,
    app_router,
    image_router,
    llm_router,
    marketplace_router,
    model_config_router,
    referral_router,
    video_router,
)
from service_routes import service_router

from shared.database import close_db, init_db
from shared.redis_client import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and Redis
    await init_db()
    await init_redis()
    print("Apps service started successfully")
    yield
    # Cleanup
    await close_db()
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title="fairydust Apps Service",
    description="App registration, management, and marketplace service",
    version="1.0.0",
    lifespan=lifespan,
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


# CORS middleware
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(app_router, prefix="/apps", tags=["apps"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(marketplace_router, prefix="/marketplace", tags=["marketplace"])
app.include_router(service_router, prefix="/service", tags=["service"])
app.include_router(llm_router, prefix="/llm", tags=["llm"])
app.include_router(model_config_router, prefix="/model-configs", tags=["model-configs"])
app.include_router(image_router, prefix="/image", tags=["image"])
app.include_router(video_router, prefix="/video", tags=["video"])
app.include_router(referral_router, prefix="/referrals", tags=["referrals"])


@app.get("/")
async def root():
    return {"message": "fairydust Apps Service is running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "apps"}


if __name__ == "__main__":
    import uvicorn

    # Configure for longer video generation requests
    timeout_seconds = int(os.getenv("REQUEST_TIMEOUT", "600"))  # Default 10 minutes

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8003)),
        timeout_keep_alive=timeout_seconds,
        timeout_graceful_shutdown=timeout_seconds,
    )
