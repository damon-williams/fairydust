# services/content/main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.database import init_db, close_db
from shared.redis_client import init_redis, close_redis
from routes import content_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database and Redis
    await init_db()
    await init_redis()
    print("Content service started successfully")
    yield
    # Cleanup
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

# Include routers
app.include_router(content_router, prefix="/recipes", tags=["recipes"])

@app.get("/")
async def root():
    return {"message": "fairydust Content Service is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "content"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8006)),
        reload=os.getenv("ENVIRONMENT", "development") == "development"
    )