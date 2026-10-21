"""
main.py — FastAPI application entry point for the CGI backend.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from database import check_database, engine

# ── Routers ───────────────────────────────────────────────────────────────────
from routers.auth                 import router as auth_router
from routers.users                import router as users_router
from routers.inspection           import router as inspection_router
from routers.transactions         import router as transactions_router
from routers.pricing              import router as pricing_router
from routers.dashboard            import router as dashboard_router
from routers.reports              import router as reports_router
from routers.hardware             import router as hardware_router
from routers.transaction_workflow import router as transaction_workflow_router

settings = get_settings()
BACKEND_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before yielding to the application."""
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    check_database()
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="Coffee Grade Identification (CGI) API",
    description="Automated coffee bean quality assessment and pricing system.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (uploaded images) ───────────────────────────────────────────
app.mount("/static/uploads", StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False), name="uploads")
app.mount("/static", StaticFiles(directory=BACKEND_DIR / "static", check_dir=False), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(inspection_router)
app.include_router(transactions_router)
app.include_router(pricing_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(hardware_router)
app.include_router(transaction_workflow_router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "version": "1.0.0"}
