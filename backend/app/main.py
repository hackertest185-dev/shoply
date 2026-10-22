"""
app/main.py
FastAPI application entry point.
Mounts all routers, configures CORS, security headers, rate limiting,
and manages DB/Redis lifecycle via startup/shutdown events.
"""
import uuid
import logging
import re
from urllib.parse import urlparse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import connect_db, close_db, get_db
from app.core.redis_client import connect_redis, close_redis, get_redis
from app.core.request_context import request_id_context
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
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


class RequestBodyLimitMiddleware:
    """Enforce the configured body limit even when Content-Length is absent."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                if int(raw_length) > self.max_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={"success": False, "error": {"code": "REQUEST_TOO_LARGE", "message": "Request body is too large."}},
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(status_code=400, content={"success": False, "error": {"code": "INVALID_CONTENT_LENGTH", "message": "Invalid request."}})
                await response(scope, receive, send)
                return

        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    raise ValueError("REQUEST_BODY_LIMIT_EXCEEDED")
            return message

        try:
            await self.app(scope, limited_receive, send)
        except ValueError as exc:
            if str(exc) != "REQUEST_BODY_LIMIT_EXCEEDED":
                raise
            response = JSONResponse(
                status_code=413,
                content={"success": False, "error": {"code": "REQUEST_TOO_LARGE", "message": "Request body is too large."}},
            )
            await response(scope, receive, send)


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
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)

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
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path in {
        f"{PREFIX}/auth/refresh",
        f"{PREFIX}/auth/logout",
    } and request.cookies.get("refresh_token"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        trusted = {urlparse(item).scheme + "://" + (urlparse(item).netloc or "") for item in settings.ALLOWED_ORIGINS}
        referer_origin = None
        if referer:
            parsed_referer = urlparse(referer)
            referer_origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}"
        # An explicitly supplied Origin is authoritative. Never let a trusted
        # Referer override a hostile Origin; only use Referer for clients that
        # omit Origin entirely.
        source_origin = origin if origin is not None else referer_origin
        if source_origin not in trusted:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": {"code": "CSRF_BLOCKED", "message": "Request origin is not trusted."}},
            )
    candidate_request_id = request.headers.get("X-Request-ID", "")
    request_id = candidate_request_id if _REQUEST_ID.fullmatch(candidate_request_id) else str(uuid.uuid4())
    context_token = request_id_context.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_context.reset(context_token)
    response.headers["X-Request-ID"]           = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["Referrer-Policy"]        = "no-referrer"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Permissions-Policy"]     = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    if request.url.path.startswith(f"{PREFIX}/auth/"):
        response.headers["Cache-Control"] = "no-store"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
    return response


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    # Pydantic's default input/ctx fields can echo passwords and recovery tokens.
    errors = [{"loc": error["loc"], "type": error["type"], "msg": error["msg"]} for error in exc.errors()]
    return JSONResponse(status_code=422, content={
        "success": False,
        "error": {"code": "VALIDATION_ERROR", "message": errors[0]["msg"] if errors else "Check the submitted fields."},
        "detail": errors,
    })


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    # Avoid copying user-controlled exception messages into centralized logs.
    logger.error("Unhandled exception [%s], type=%s", request_id, type(exc).__name__)
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
