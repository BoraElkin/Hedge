"""FastAPI application for HVAC Copilot.

Handles:
- Authentication (via Supabase)
- Session management
- Task templates
- Usage tracking for free tier limits
- Static file serving for web chat UI
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import auth, sessions, tasks, usage

# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("HVAC Copilot API starting...")
    yield
    # Shutdown
    print("HVAC Copilot API shutting down...")


app = FastAPI(
    title="HVAC Copilot API",
    description="Real-time AI guidance for HVAC technicians",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - allow mobile app to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",  # Expo dev
        "http://localhost:19006",  # Expo web
        "exp://localhost:8081",  # Expo Go
        "*",  # TODO: Restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(usage.router, prefix="/usage", tags=["usage"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "name": "HVAC Copilot API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "services": {
            "api": "up",
            "database": "up",  # TODO: Actually check Supabase
        },
    }


# Mount static files for web chat UI
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/chat")
async def chat_ui():
    """Serve the web chat UI."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"error": "Chat UI not found. Static files may not be installed."}
