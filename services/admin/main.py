from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.database import init_db, close_db, get_db, Database
from shared.redis_client import init_redis, close_redis

app = FastAPI(title="Fairydust Admin Portal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files first
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

from routes import admin_router

app.include_router(admin_router, prefix="/admin")

@app.on_event("startup")
async def startup():
    await init_db()
    await init_redis()

@app.on_event("shutdown")
async def shutdown():
    await close_db()
    await close_redis()

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/login")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "admin"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)