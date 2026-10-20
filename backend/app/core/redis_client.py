"""
core/redis_client.py
Async Redis connection via redis-py.
Handles OTP storage (bcrypt-hashed, TTL-bound) and rate-limit counters.
"""
import json
import hashlib
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
PASSWORD_RESET_KEY_PREFIX = "password_reset:"
ADMIN_MFA_KEY_PREFIX = "admin_mfa:"
ADMIN_MFA_ATTEMPTS_KEY_PREFIX = "admin_mfa_attempts:"
LOGIN_CHALLENGE_KEY_PREFIX = "login_challenge:"
LOGIN_CHALLENGE_ATTEMPTS_KEY_PREFIX = "login_challenge_attempts:"


def _email_key(email: str) -> str:
    """Use a deterministic hash so raw email addresses never become Redis keys."""
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


async def consume_rate_limit(bucket: str, identity: str, limit: int, window_seconds: int) -> bool:
    """Small atomic-ish Redis counter for account/challenge-specific limits."""
    try:
        redis = get_redis()
    except RuntimeError:
        # The request still has slowapi's IP limiter.  This fallback keeps
        # dependency-injected tests and emergency health endpoints usable;
        # production readiness remains unhealthy until Redis is restored.
        return True
    digest = hashlib.sha256(str(identity).encode()).hexdigest()
    key = f"rate:{bucket}:{digest}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count <= limit


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
    key = _email_key(email)
    otp_hash = bcrypt.hashpw(otp_plaintext.encode(), bcrypt.gensalt(rounds=10)).decode()
    await redis.set(f"{EMAIL_OTP_KEY_PREFIX}{key}", otp_hash, ex=settings.EMAIL_OTP_TTL_SECONDS)
    await redis.delete(f"{EMAIL_OTP_ATTEMPTS_KEY_PREFIX}{key}")
    await redis.delete(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}")


async def verify_email_otp(email: str, submitted: str) -> dict[str, Any]:
    redis = get_redis()
    key = _email_key(email)
    if await redis.exists(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}"):
        return {"valid": False, "locked": True, "attempts_remaining": 0}
    stored_hash = await redis.get(f"{EMAIL_OTP_KEY_PREFIX}{key}")
    if not stored_hash:
        return {"valid": False, "locked": False, "expired": True, "attempts_remaining": 0}
    if bcrypt.checkpw(submitted.encode(), stored_hash.encode()):
        # GETDEL makes concurrent uses of the same code one-time as well.
        claimed = await redis.getdel(f"{EMAIL_OTP_KEY_PREFIX}{key}")
        if claimed != stored_hash:
            return {"valid": False, "locked": False, "expired": True, "attempts_remaining": 0}
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
    key = _email_key(email)
    await redis.delete(f"{EMAIL_OTP_KEY_PREFIX}{key}")
    await redis.delete(f"{EMAIL_OTP_ATTEMPTS_KEY_PREFIX}{key}")
    await redis.delete(f"{EMAIL_OTP_LOCK_KEY_PREFIX}{key}")


async def store_password_reset_token(token: str, user_id: str, auth_version: int, ttl: int = 1800) -> None:
    redis = get_redis()
    digest = hashlib.sha256(token.encode()).hexdigest()
    await redis.set(
        f"{PASSWORD_RESET_KEY_PREFIX}{digest}",
        json.dumps({"user_id": user_id, "auth_version": auth_version, "purpose": "password_reset"}),
        ex=ttl,
    )


async def consume_password_reset_token(token: str) -> dict[str, Any] | None:
    redis = get_redis()
    digest = hashlib.sha256(token.encode()).hexdigest()
    key = f"{PASSWORD_RESET_KEY_PREFIX}{digest}"
    value = await redis.getdel(key)
    if not value:
        return None
    try:
        claim = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(claim, dict) or claim.get("purpose") != "password_reset":
        return None
    if not isinstance(claim.get("user_id"), str) or not isinstance(claim.get("auth_version"), int):
        return None
    return claim


async def store_admin_mfa_challenge(
    challenge_id: str,
    user_id: str,
    otp_plaintext: str,
    ip_hash: str,
    ttl: int,
) -> None:
    """Store only a bcrypt OTP hash and minimal challenge metadata."""
    redis = get_redis()
    key = f"{ADMIN_MFA_KEY_PREFIX}{hashlib.sha256(challenge_id.encode()).hexdigest()}"
    otp_hash = bcrypt.hashpw(otp_plaintext.encode(), bcrypt.gensalt(rounds=10)).decode()
    await redis.hset(key, mapping={"user_id": user_id, "otp_hash": otp_hash, "ip_hash": ip_hash})
    await redis.expire(key, ttl)
    await redis.delete(f"{ADMIN_MFA_ATTEMPTS_KEY_PREFIX}{hashlib.sha256(challenge_id.encode()).hexdigest()}")


async def verify_admin_mfa_challenge(
    challenge_id: str,
    submitted: str,
    max_attempts: int,
    ttl: int,
) -> dict[str, Any]:
    redis = get_redis()
    digest = hashlib.sha256(challenge_id.encode()).hexdigest()
    key = f"{ADMIN_MFA_KEY_PREFIX}{digest}"
    attempts_key = f"{ADMIN_MFA_ATTEMPTS_KEY_PREFIX}{digest}"
    challenge = await redis.hgetall(key)
    if not challenge:
        return {"valid": False, "expired": True, "locked": False}
    if bcrypt.checkpw(submitted.encode(), challenge["otp_hash"].encode()):
        await redis.delete(key, attempts_key)
        return {"valid": True, "user_id": challenge["user_id"]}
    attempts = await redis.incr(attempts_key)
    await redis.expire(attempts_key, ttl)
    remaining = max(0, max_attempts - attempts)
    if attempts >= max_attempts:
        await redis.delete(key)
        return {"valid": False, "locked": True, "attempts_remaining": 0, "user_id": challenge.get("user_id")}
    return {"valid": False, "locked": False, "attempts_remaining": remaining, "user_id": challenge.get("user_id")}


def _login_challenge_keys(challenge_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(challenge_id.encode()).hexdigest()
    return f"{LOGIN_CHALLENGE_KEY_PREFIX}{digest}", f"{LOGIN_CHALLENGE_ATTEMPTS_KEY_PREFIX}{digest}"


async def store_login_challenge(
    challenge_id: str, user_id: str, auth_version: int, otp: str, ttl: int
) -> None:
    """Store a one-time password-verified login challenge without plaintext OTP."""
    redis = get_redis()
    key, attempts_key = _login_challenge_keys(challenge_id)
    payload = {
        "purpose": "password_login",
        "user_id": user_id,
        "auth_version": auth_version,
        "otp_hash": bcrypt.hashpw(otp.encode(), bcrypt.gensalt(rounds=10)).decode(),
    }
    await redis.set(key, json.dumps(payload), ex=ttl)
    await redis.delete(attempts_key)


async def delete_login_challenge(challenge_id: str) -> None:
    redis = get_redis()
    key, attempts_key = _login_challenge_keys(challenge_id)
    await redis.delete(key, attempts_key)


async def verify_login_challenge(
    challenge_id: str, otp: str, max_attempts: int, ttl: int
) -> dict[str, Any]:
    redis = get_redis()
    key, attempts_key = _login_challenge_keys(challenge_id)
    raw = await redis.get(key)
    if not raw:
        return {"valid": False, "expired": True}
    try:
        payload = json.loads(raw)
        if payload.get("purpose") != "password_login":
            return {"valid": False, "expired": True}
        otp_hash = payload["otp_hash"]
        user_id = payload["user_id"]
        auth_version = payload["auth_version"]
        if not isinstance(user_id, str) or not isinstance(auth_version, int):
            return {"valid": False, "expired": True}
    except (TypeError, ValueError, KeyError):
        return {"valid": False, "expired": True}

    if bcrypt.checkpw(otp.encode(), otp_hash.encode()):
        # GETDEL ensures two parallel submissions cannot both issue a session.
        claimed = await redis.getdel(key)
        if claimed != raw:
            return {"valid": False, "expired": True}
        await redis.delete(attempts_key)
        return {"valid": True, "user_id": user_id, "auth_version": auth_version}

    attempts = await redis.incr(attempts_key)
    await redis.expire(attempts_key, ttl)
    if attempts >= max_attempts:
        await redis.delete(key)
        return {"valid": False, "locked": True, "user_id": user_id}
    return {"valid": False, "locked": False, "user_id": user_id}


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
