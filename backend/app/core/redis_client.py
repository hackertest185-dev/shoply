"""
core/redis_client.py
Async Redis connection via redis-py.
Handles OTP storage (bcrypt-hashed, TTL-bound) and rate-limit counters.
"""
import json
from typing import Any

import redis.asyncio as aioredis
import bcrypt

from .config import settings

_redis: aioredis.Redis | None = None


async def connect_redis() -> None:
    global _redis
    _redis = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not connected. Call connect_redis() first.")
    return _redis


# ── OTP helpers ───────────────────────────────────────────────────────────────

OTP_KEY_PREFIX = "otp:"
OTP_ATTEMPTS_KEY_PREFIX = "otp_attempts:"
OTP_LOCK_KEY_PREFIX = "otp_lock:"
EMAIL_OTP_KEY_PREFIX = "email_otp:"
EMAIL_OTP_ATTEMPTS_KEY_PREFIX = "email_otp_attempts:"
EMAIL_OTP_LOCK_KEY_PREFIX = "email_otp_lock:"


async def store_otp(order_id: str, otp_plaintext: str) -> None:
    """
    Hash and store OTP in Redis with TTL.
    Plaintext is NEVER persisted — only bcrypt hash.
    """
    redis = get_redis()
    otp_hash = bcrypt.hashpw(otp_plaintext.encode(), bcrypt.gensalt(rounds=10)).decode()
    await redis.set(f"{OTP_KEY_PREFIX}{order_id}", otp_hash, ex=settings.OTP_TTL_SECONDS)
    # Reset attempt counter
    await redis.delete(f"{OTP_ATTEMPTS_KEY_PREFIX}{order_id}")


async def verify_otp(order_id: str, submitted: str) -> dict[str, Any]:
    """
    Validate submitted OTP against stored hash.
    Returns: { "valid": bool, "attempts_remaining": int, "locked": bool }
    Deletes OTP from Redis on success (one-time use).
    """
    redis = get_redis()

    # Check if locked
    if await redis.exists(f"{OTP_LOCK_KEY_PREFIX}{order_id}"):
        return {"valid": False, "attempts_remaining": 0, "locked": True}

    stored_hash = await redis.get(f"{OTP_KEY_PREFIX}{order_id}")
    if not stored_hash:
        return {"valid": False, "attempts_remaining": 0, "locked": False, "expired": True}

    is_valid = bcrypt.checkpw(submitted.encode(), stored_hash.encode())

    if is_valid:
        # One-time use — delete immediately
        await redis.delete(f"{OTP_KEY_PREFIX}{order_id}")
        await redis.delete(f"{OTP_ATTEMPTS_KEY_PREFIX}{order_id}")
        return {"valid": True, "attempts_remaining": settings.OTP_MAX_ATTEMPTS, "locked": False}

    # Increment attempt counter
    attempts_key = f"{OTP_ATTEMPTS_KEY_PREFIX}{order_id}"
    attempts = await redis.incr(attempts_key)
    await redis.expire(attempts_key, settings.OTP_TTL_SECONDS)
    remaining = max(0, settings.OTP_MAX_ATTEMPTS - attempts)

    if attempts >= settings.OTP_MAX_ATTEMPTS:
        # Lock the order and invalidate OTP
        await redis.set(
            f"{OTP_LOCK_KEY_PREFIX}{order_id}", "1", ex=settings.OTP_LOCK_SECONDS
        )
        await redis.delete(f"{OTP_KEY_PREFIX}{order_id}")
        return {"valid": False, "attempts_remaining": 0, "locked": True, "just_locked": True}

    return {"valid": False, "attempts_remaining": remaining, "locked": False}


async def delete_otp(order_id: str) -> None:
    redis = get_redis()
    await redis.delete(f"{OTP_KEY_PREFIX}{order_id}")
    await redis.delete(f"{OTP_ATTEMPTS_KEY_PREFIX}{order_id}")


async def store_email_otp(email: str, otp_plaintext: str) -> None:
    """Store a hashed email OTP; the plaintext never enters Redis."""
    redis = get_redis()
    key = email.lower().strip()
    otp_hash = bcrypt.hashpw(otp_plaintext.encode(), bcrypt.gensalt(rounds=10)).decode()
    await redis.set(f"{EMAIL_OTP_KEY_PREFIX}{key}", otp_hash, ex=settings.EMAIL_OTP_TTL_SECONDS)
    await redis.delete(f"{EMAIL_OTP_ATTEMPTS_KEY_PREFIX}{key}")
    await redis.delete(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}")


async def verify_email_otp(email: str, submitted: str) -> dict[str, Any]:
    redis = get_redis()
    key = email.lower().strip()
    if await redis.exists(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}"):
        return {"valid": False, "locked": True, "attempts_remaining": 0}
    stored_hash = await redis.get(f"{EMAIL_OTP_KEY_PREFIX}{key}")
    if not stored_hash:
        return {"valid": False, "locked": False, "expired": True, "attempts_remaining": 0}
    if bcrypt.checkpw(submitted.encode(), stored_hash.encode()):
        await redis.delete(f"{EMAIL_OTP_KEY_PREFIX}{key}")
        await redis.delete(f"{EMAIL_OTP_ATTEMPTS_KEY_PREFIX}{key}")
        return {"valid": True, "locked": False, "attempts_remaining": settings.EMAIL_OTP_MAX_ATTEMPTS}
    attempts_key = f"{EMAIL_OTP_ATTEMPTS_KEY_PREFIX}{key}"
    attempts = await redis.incr(attempts_key)
    await redis.expire(attempts_key, settings.EMAIL_OTP_TTL_SECONDS)
    remaining = max(0, settings.EMAIL_OTP_MAX_ATTEMPTS - attempts)
    if attempts >= settings.EMAIL_OTP_MAX_ATTEMPTS:
        await redis.set(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}", "1", ex=settings.EMAIL_OTP_TTL_SECONDS)
        await redis.delete(f"{EMAIL_OTP_KEY_PREFIX}{key}")
        return {"valid": False, "locked": True, "attempts_remaining": 0}
    return {"valid": False, "locked": False, "attempts_remaining": remaining}


async def delete_email_otp(email: str) -> None:
    redis = get_redis()
    key = email.lower().strip()
    await redis.delete(f"{EMAIL_OTP_KEY_PREFIX}{key}")
    await redis.delete(f"{EMAIL_OTP_ATTEMPTS_KEY_PREFIX}{key}")
    await redis.delete(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}")


# ── Generic cache helpers ─────────────────────────────────────────────────────

async def cache_set(key: str, value: Any, ttl: int) -> None:
    redis = get_redis()
    await redis.set(key, json.dumps(value), ex=ttl)


async def cache_get(key: str) -> Any | None:
    redis = get_redis()
    raw = await redis.get(key)
    return json.loads(raw) if raw else None


async def cache_delete(key: str) -> None:
    redis = get_redis()
    await redis.delete(key)
