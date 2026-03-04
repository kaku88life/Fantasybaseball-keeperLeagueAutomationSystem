"""
Fantasy Baseball Keeper League - FastAPI Application Entry Point
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is on the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(project_root / ".env")

from api.database import init_db
from api.routers import auth, commissioner, league, teams, validation


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    await init_db()
    yield


app = FastAPI(
    title="5-Man MLB Keeper League API",
    description="Fantasy Baseball Keeper League Automation System",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(league.router, prefix="/api/league", tags=["league"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(commissioner.router, prefix="/api/commissioner", tags=["commissioner"])
app.include_router(validation.router, prefix="/api/validate", tags=["validation"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "keeper-league-api"}
