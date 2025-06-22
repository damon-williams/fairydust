from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from pathlib import Path

from shared.database import init_db, close_db
from shared.redis_client import init_redis, close_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting admin service initialization...")
        
        # Set environment variable to skip schema init for admin service
        # since other services will create the tables
        os.environ.setdefault("SKIP_SCHEMA_INIT", "true")
        
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
    title="Fairydust Admin Portal", 
    version="1.0.0",
    description="Admin portal for fairydust platform",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

from routes import admin_router

app.include_router(admin_router, prefix="/admin")

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/login")

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
        reload=os.getenv("ENVIRONMENT", "development") == "development"
    )