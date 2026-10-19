"""
app/main.py
FastAPI application entry point.
Mounts all routers, configures CORS, security headers, rate limiting,
and manages DB/Redis lifecycle via startup/shutdown events.
"""
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import connect_db, close_db, get_db
from app.core.redis_client import connect_redis, close_redis, get_redis
from app.routers import (
    auth_router,
    products_router,
    categories_router,
    cart_router,
    orders_router,
    addresses_router,
    delivery_router,
    admin_router,
    wishlist_router,
    coupons_router,
    chat_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shoply")


# ── Lifespan (startup + shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — connecting DB and Redis...")
    settings.validate_runtime()
    await connect_db()
    await connect_redis()
    logger.info("Ready.")
    yield
    logger.info("Shutting down...")
    await close_db()
    await close_redis()


# ── App instance ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,   # Disable /docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,   # Never "*" in production
    allow_credentials=True,                   # Required for HttpOnly cookie
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-Request-ID"],
    max_age=600,
)


# ── Security headers middleware ────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"]           = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]     = "camera=(), microphone=(), geolocation=(), payment=(self)"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
    return response


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    logger.error("Unhandled exception [%s]: %s", request_id, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success":    False,
            "error":      {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."},
            "request_id": request_id,
        },
    )


# ── Health check (public — no auth) ──────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Dependency-aware readiness probe for Render and smoke tests."""
    checks = {"mongodb": False, "redis": False}
    try:
        await get_db().command("ping")
        checks["mongodb"] = True
    except Exception:
        logger.warning("MongoDB readiness check failed", exc_info=True)
    try:
        await get_redis().ping()
        checks["redis"] = True
    except Exception:
        logger.warning("Redis readiness check failed", exc_info=True)

    healthy = all(checks.values())
    payload = {"status": "ready" if healthy else "not_ready", "checks": checks}
    return JSONResponse(status_code=200 if healthy else 503, content=payload)


# ── Register routers under /api/v1 ────────────────────────────────────────────
PREFIX = "/api/v1"

app.include_router(auth_router.router,     prefix=PREFIX)
app.include_router(products_router.router, prefix=PREFIX)
app.include_router(categories_router.router, prefix=PREFIX)
app.include_router(cart_router.router,     prefix=PREFIX)
app.include_router(orders_router.router,   prefix=PREFIX)
app.include_router(addresses_router.router, prefix=PREFIX)
if settings.ENABLE_LEGACY_DELIVERY:
    app.include_router(delivery_router.router, prefix=PREFIX)
app.include_router(admin_router.router,    prefix=PREFIX)
app.include_router(wishlist_router.router, prefix=PREFIX)
app.include_router(coupons_router.router, prefix=PREFIX)
app.include_router(chat_router.router, prefix=PREFIX)
