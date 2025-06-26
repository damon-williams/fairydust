# services/ledger/main.py
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

# Import our routes and dependencies
from background import start_background_tasks, stop_background_tasks
from routes import admin_router, balance_router, transaction_router

from shared.database import close_db, init_db
from shared.redis_client import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await init_redis()
    await start_background_tasks()
    yield
    # Shutdown
    await stop_background_tasks()
    await close_db()
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title="fairydust Ledger Service",
    version="1.0.0",
    description="DUST balance and transaction management for fairydust platform",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ledger", "version": "1.0.0"}


# Include routers
app.include_router(balance_router, prefix="/balance", tags=["balance"])
app.include_router(transaction_router, prefix="/transactions", tags=["transactions"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
