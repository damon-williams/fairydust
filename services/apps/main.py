# services/apps/main.py
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import admin_router, app_router, llm_router, marketplace_router
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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


@app.get("/")
async def root():
    return {"message": "fairydust Apps Service is running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "apps"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8003)))
