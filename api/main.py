"""
Fantasy Baseball Keeper League - FastAPI Application Entry Point
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path

# Ensure project root is on the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

load_dotenv(project_root / ".env")

from api.database import (
    cleanup_old_job_runs,
    cleanup_old_notifications,
    init_db,
    seed_if_empty,
)
from api.routers import analytics, auth, commissioner, league, players, public, teams, validation


def _deferred_startup_refresh():
    """Heavy, Yahoo-dependent startup work — runs off the startup path.

    These calls are rate-limited (2s/request) and retry 429s with 60-300s
    sleeps, so running them inline used to block the event loop for minutes and
    could get the container killed before the scheduler was ever registered.
    """
    from api.database import record_job_run

    # Refresh 2026 post-draft snapshot (keepers + draft merge).
    try:
        from scripts.update_2026_post_draft import run_post_draft_update
        result = run_post_draft_update(verbose=False)
        print(f"[Startup] 2026 post-draft snapshot refreshed: {result}", flush=True)
    except FileNotFoundError as e:
        print(f"[Startup] 2026 post-draft skipped (missing data file): {e}", flush=True)
    except Exception as e:
        print(f"[Startup] 2026 post-draft load error (non-fatal): {e}", flush=True)
        traceback.print_exc()

    # Refresh current-year transactions JSON.
    # Zeabur container filesystem is ephemeral — redeploy reverts this file to
    # the git baseline (commish-only), wiping FAAB pickup stats. Re-fetch from
    # Yahoo API on startup to restore analytics immediately.
    try:
        import json as _json
        from datetime import datetime as _dt
        from pathlib import Path as _Path
        from api.yahoo_service import discover_league_keys, fetch_transactions_full

        _year = _dt.now().year
        _keys = discover_league_keys()
        if _year in _keys:
            _txs = fetch_transactions_full(_keys[_year])
            _path = _Path(__file__).resolve().parents[1] / "data" / f"yahoo_{_year}_transactions.json"
            _path.write_text(_json.dumps(_txs, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[Startup] Refreshed {_year} transactions: {len(_txs.get('transactions', []))} records", flush=True)
            record_job_run("startup_refresh", "success", f"{len(_txs.get('transactions', []))} transactions")
        else:
            print(f"[Startup] No Yahoo league for year {_year}; skip transaction refresh", flush=True)
            record_job_run("startup_refresh", "skipped", f"no Yahoo league for {_year}")
    except Exception as e:
        print(f"[Startup] Transaction refresh error (non-fatal): {e}", flush=True)
        record_job_run("startup_refresh", "failed", str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events.

    Order matters: the scheduler is registered as early as possible so a slow or
    failing data refresh can never stop the weekly/monthly reports from being
    scheduled.
    """
    try:
        await init_db()
        seed_if_empty()
    except Exception as e:
        print(f"[Startup] DB init/seed error (non-fatal): {e}", flush=True)
        traceback.print_exc()

    # Start reminder scheduler (no-op if env vars not configured)
    try:
        from src.notification.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"[Startup] Scheduler error (non-fatal): {e}", flush=True)
        traceback.print_exc()

    # Everything below is best-effort maintenance — deliberately off the
    # startup path so the container becomes healthy immediately.
    def _background_startup():
        try:
            cleanup_old_notifications(retention_days=365)
            cleanup_old_job_runs(retention_days=90)
        except Exception as e:
            print(f"[Startup] Cleanup error (non-fatal): {e}", flush=True)

        # Re-send any weekly/monthly report whose trigger time passed while the
        # container was down. No-ops when the last run already succeeded.
        try:
            from src.notification.scheduler import run_startup_catchup
            print(f"[Startup] Report catch-up: {run_startup_catchup()}", flush=True)
        except Exception as e:
            print(f"[Startup] Report catch-up error (non-fatal): {e}", flush=True)

        _deferred_startup_refresh()

    threading.Thread(
        target=_background_startup,
        name="startup-refresh",
        daemon=True,
    ).start()

    yield

    try:
        from src.notification.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass


app = FastAPI(
    title="Fantasy Baseball 5-Man Keepers API",
    description="Fantasy Baseball 5-Man Keepers Automation System",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - production origins via ALLOWED_ORIGINS env var (comma-separated)
_default_origins = [
    # Production (Zeabur)
    "https://5man-keeperleague.zeabur.app",
    # Local development
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]
_extra = os.getenv("ALLOWED_ORIGINS", "")
_extra_origins = [o.strip() for o in _extra.split(",") if o.strip()] if _extra else []
_frontend_url = os.getenv("FRONTEND_URL", "")
# Ensure FRONTEND_URL has https:// prefix
if _frontend_url and not _frontend_url.startswith("http"):
    _frontend_url = f"https://{_frontend_url}"
_all_origins = list(dict.fromkeys(
    _extra_origins + ([_frontend_url] if _frontend_url else []) + _default_origins
))
print(f"[CORS] Allowed origins: {_all_origins}")

_all_origins_set = set(_all_origins)


def _add_cors_headers(response: JSONResponse, origin: str):
    """Manually add CORS headers to a response."""
    if origin and origin in _all_origins_set:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"


app.add_middleware(
    CORSMiddleware,
    allow_origins=_all_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression for responses > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(league.router, prefix="/api/league", tags=["league"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(commissioner.router, prefix="/api/commissioner", tags=["commissioner"])
app.include_router(validation.router, prefix="/api/validate", tags=["validation"])
app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(public.router, prefix="/api/public", tags=["public"])


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # HSTS only in production (HTTPS)
    if _is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


_is_production = bool(os.getenv("FRONTEND_URL", "").startswith("https"))


@app.middleware("http")
async def catch_all_errors_middleware(request: Request, call_next):
    """Catch unhandled exceptions inside CORSMiddleware scope.
    Returns proper JSONResponse so CORSMiddleware can add CORS headers.
    Also manually adds CORS headers as a fallback safety net."""
    origin = request.headers.get("origin", "")
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        print(f"[ERROR] {request.method} {request.url.path}: {exc}", flush=True)
        traceback.print_exc()
        # Hide internal details in production
        detail = (
            "Internal server error"
            if _is_production
            else f"Internal server error: {type(exc).__name__}: {exc}"
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": detail},
        )
        _add_cors_headers(response, origin)
        return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Fallback: catch exceptions that bypass the middleware.
    Manually adds CORS headers since this handler's response
    may not flow through CORSMiddleware."""
    print(f"[ERROR-HANDLER] {request.method} {request.url.path}: {exc}", flush=True)
    traceback.print_exc()
    origin = request.headers.get("origin", "")
    # Hide internal details in production
    detail = (
        "Internal server error"
        if _is_production
        else f"Internal server error: {type(exc).__name__}: {exc}"
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": detail},
    )
    _add_cors_headers(response, origin)
    return response


from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException as FastAPIHTTPException


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """Ensure CORS headers on all HTTP error responses (401, 403, etc.)."""
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
    _add_cors_headers(response, origin)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure CORS headers on validation error responses."""
    origin = request.headers.get("origin", "")
    response = JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )
    _add_cors_headers(response, origin)
    return response


@app.get("/")
async def root():
    return {"status": "ok", "service": "keeper-league-api", "docs": "/docs"}


@app.get("/api/debug/cors")
async def debug_cors(request: Request):
    """Debug endpoint to verify CORS headers are working."""
    origin = request.headers.get("origin", "")
    return {
        "origin_received": origin,
        "origin_allowed": origin in _all_origins_set if origin else None,
        "all_origins": _all_origins,
        "headers": dict(request.headers),
    }


@app.get("/api/health")
async def health_check():
    """Health check with DB connectivity test."""
    db_status = "unknown"
    db_error = ""
    try:
        from api.database import get_db
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            db_status = "ok"
        finally:
            conn.close()
    except Exception as e:
        db_status = "error"
        db_error = str(e)

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": "keeper-league-api",
        "database": db_status,
        "database_error": db_error or None,
        "cors_origins_count": len(_all_origins),
    }


