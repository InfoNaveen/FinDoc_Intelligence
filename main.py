"""
FinDoc Intelligence Pipeline — FastAPI Entry Point
HyperAPI is the only external dependency. No external AI services.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import UPLOAD_DIR, USE_MOCK_HYPER_API
from database.db import init_db
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("=" * 60)
    logger.info("🚀 FinDoc Intelligence Pipeline — Starting up")
    logger.info(f"   Mock mode: {USE_MOCK_HYPER_API}")
    logger.info(f"   External deps: HyperAPI only")
    logger.info("=" * 60)

    # Initialize database
    init_db()

    # Create upload directory
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    yield

    # Shutdown
    logger.info("FinDoc Intelligence Pipeline — Shutting down")


app = FastAPI(
    title="FinDoc Intelligence Pipeline",
    description="AI-powered financial document extraction, validation, and scoring. Powered by HyperAPI.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    return {
        "name": "FinDoc Intelligence Pipeline",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "powered_by": "HyperAPI",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
