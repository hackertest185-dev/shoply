"""
core/security.py
JWT creation/decode (RS256), bcrypt hashing, token utilities.
Never import this module's internals directly — use via dependencies/.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import settings


# ── bcrypt ────────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a password with bcrypt (12 rounds). Call immediately on receipt."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """
    Constant-time comparison. Always runs even if user not found
    (call with a dummy hash) — prevents timing-based email enumeration.
    """
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


DUMMY_HASH = hash_password("dummy_password_for_timing_equalization")


# ── JWT ───────────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(payload: dict[str, Any]) -> str:
    """
    Create a short-lived RS256 access token.
    Payload must include: user_id, email, role.
    """
    now = _now_utc()
    claims = {
        **payload,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "jti": secrets.token_hex(16),   # unique token ID for revocation
    }
    return jwt.encode(claims, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, token_family: str) -> tuple[str, str]:
    """
    Create a long-lived refresh token.
    Returns (plaintext_token, sha256_hash_for_storage).
    Only the hash is stored — plaintext goes in the cookie.
    token_family: UUID grouping tokens for reuse detection.
    """
    now = _now_utc()
    jti = secrets.token_hex(16)
    claims = {
        "user_id": user_id,
        "token_family": token_family,
        "exp": now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": now,
        "jti": jti,
    }
    plaintext = jwt.encode(claims, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)
    stored_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, stored_hash


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate an access token.
    Raises PyJWTError on failure (expired, tampered, wrong key).
    """
    return jwt.decode(token, settings.JWT_PUBLIC_KEY, algorithms=[settings.JWT_ALGORITHM])


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode a refresh token — same key, same algorithm."""
    return jwt.decode(token, settings.JWT_PUBLIC_KEY, algorithms=[settings.JWT_ALGORITHM])


def hash_token(token: str) -> str:
    """SHA-256 hash a token for safe DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Verification / reset tokens ───────────────────────────────────────────────

def generate_secure_token() -> tuple[str, str]:
    """
    Generate a URL-safe random token for email verification / password reset.
    Returns (plaintext, sha256_hash). Store hash, send plaintext.
    TTL is enforced in the DB document (expires_at field).
    """
    plaintext = secrets.token_urlsafe(32)
    stored_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, stored_hash
