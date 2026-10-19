"""
services/auth_service.py
All authentication business logic. No HTTP concepts - pure Python.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.core.config import settings
from app.core.redis_client import (
    store_admin_mfa_challenge,
    verify_admin_mfa_challenge,
)
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import user_model
from app.services.audit_log_service import write_audit_log
from app.services.email_service import email_is_configured, send_email_otp


MAX_FAILED_LOGINS = 10
LOCKOUT_MINUTES = 30


def _safe_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "verification_status": user.get("verification_status"),
    }


async def _issue_session(
    db,
    user: dict,
    ip: str,
    event: str = "login_success",
    amr: tuple[str, ...] = ("email_otp",),
) -> dict:
    """Issue a short-lived access token and a rotated refresh token."""
    user_id_str = str(user["_id"])
    token_family = secrets.token_hex(16)
    auth_version = int(user.get("auth_version", 1))
    is_admin = user.get("role") == "admin"
    access_minutes = (
        settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES
        if is_admin else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    refresh_days = (
        settings.ADMIN_REFRESH_TOKEN_EXPIRE_DAYS
        if is_admin else settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    access_token = create_access_token(
        {
            "user_id": user_id_str,
            "email": user["email"],
            "role": user["role"],
            "auth_version": auth_version,
            "amr": list(amr),
        },
        expires_minutes=access_minutes,
    )
    refresh_plaintext, refresh_hash = create_refresh_token(
        user_id_str, token_family, refresh_days
    )
    await db.refresh_tokens.insert_one(
        {
            "user_id": user_id_str,
            "token_hash": refresh_hash,
            "token_family": token_family,
            "is_revoked": False,
            "auth_version": auth_version,
            "amr": list(amr),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=refresh_days),
        }
    )
    await write_audit_log(
        db,
        user_id_str,
        user["role"],
        event,
        "users",
        user_id_str,
        {"ip": ip, "method": "+".join(amr)},
        ip,
    )
    return {
        "access_token": access_token,
        "refresh_token_plain": refresh_plaintext,
        "expires_in": access_minutes * 60,
        "user": _safe_user(user),
    }


async def revoke_all_sessions(db, user_id: str) -> None:
    await db.refresh_tokens.update_many(
        {"user_id": {"$eq": user_id}},
        {"$set": {"is_revoked": True}},
    )


async def register_user(db, name: str, email: str, password: str, role: str) -> dict:
    """Create customer accounts only. Admin accounts are DB-managed."""
    if role != "customer":
        raise ValueError("invalid_registration_role")
    email_lower = email.lower().strip()
    if await user_model.find_by_email(db, email_lower):
        raise ValueError("email_conflict")

    user_id = await user_model.insert_user(
        db,
        {
            "name": name.strip(),
            "email": email_lower,
            "password_hash": hash_password(password),
            "role": "customer",
            "is_verified": True,
            "verification_status": None,
            "profile_photo_url": None,
            "addresses": [],
            "wishlist": [],
            "verification_token": None,
            "verification_token_expires": None,
        },
    )
    return {"user_id": user_id}


async def authenticate_user(db, email: str, password: str, ip: str) -> dict:
    """Authenticate with a password; admin accounts require a second factor."""
    email_lower = email.lower().strip()
    user = await user_model.find_by_email(db, email_lower)
    if not user:
        verify_password(password, DUMMY_HASH)
        raise ValueError("INVALID_CREDENTIALS")

    locked_until = user.get("account_locked_until")
    if locked_until and locked_until > datetime.now(timezone.utc):
        raise ValueError("ACCOUNT_LOCKED")

    if not verify_password(password, user.get("password_hash", "")):
        count = await user_model.increment_failed_logins(db, str(user["_id"]))
        if count >= MAX_FAILED_LOGINS:
            await user_model.update_user(
                db,
                str(user["_id"]),
                {
                    "account_locked_until": datetime.now(timezone.utc)
                    + timedelta(minutes=LOCKOUT_MINUTES)
                },
                allow_sensitive=True,
            )
            await write_audit_log(
                db,
                str(user["_id"]),
                user.get("role", "unknown"),
                "account_locked",
                "users",
                str(user["_id"]),
                {"ip": ip},
                ip,
            )
        await write_audit_log(
            db,
            str(user["_id"]),
            user.get("role", "unknown"),
            "login_failure",
            "users",
            str(user["_id"]),
            {"ip": ip},
            ip,
        )
        raise ValueError("INVALID_CREDENTIALS")

    if not user.get("is_verified") or user.get("status", "active") != "active":
        raise ValueError("INVALID_CREDENTIALS")

    await user_model.reset_failed_logins(db, str(user["_id"]))

    if user.get("role") == "admin":
        if not email_is_configured():
            await write_audit_log(
                db,
                str(user["_id"]),
                "admin",
                "admin_mfa_unavailable",
                "users",
                str(user["_id"]),
                {"ip": ip},
                ip,
            )
            raise ValueError("MFA_UNAVAILABLE")

        challenge_id = secrets.token_urlsafe(32)
        otp = str(secrets.randbelow(1_000_000)).zfill(6)
        await store_admin_mfa_challenge(
            challenge_id,
            str(user["_id"]),
            otp,
            hashlib.sha256(ip.encode()).hexdigest(),
            settings.ADMIN_MFA_TTL_SECONDS,
        )
        try:
            await send_email_otp(user["email"], otp)
        except Exception:
            await write_audit_log(
                db,
                str(user["_id"]),
                "admin",
                "admin_mfa_delivery_failed",
                "users",
                str(user["_id"]),
                {"ip": ip},
                ip,
            )
            raise ValueError("MFA_DELIVERY_FAILED")

        await write_audit_log(
            db,
            str(user["_id"]),
            "admin",
            "admin_mfa_requested",
            "users",
            str(user["_id"]),
            {"ip": ip},
            ip,
        )
        return {
            "mfa_required": True,
            "challenge_id": challenge_id,
            "expires_in": settings.ADMIN_MFA_TTL_SECONDS,
            "user": {"email": user["email"], "role": "admin"},
        }

    return await _issue_session(db, user, ip, "login_success", ("password",))


async def verify_admin_mfa(db, challenge_id: str, otp: str, ip: str) -> dict:
    """Consume an admin MFA challenge and issue a fully authenticated session."""
    result = await verify_admin_mfa_challenge(
        challenge_id,
        otp,
        settings.ADMIN_MFA_MAX_ATTEMPTS,
        settings.ADMIN_MFA_TTL_SECONDS,
    )
    if not result.get("valid"):
        event = "admin_mfa_locked" if result.get("locked") else "admin_mfa_failure"
        if result.get("user_id"):
            await write_audit_log(
                db,
                result["user_id"],
                "admin",
                event,
                "users",
                result["user_id"],
                {"ip": ip},
                ip,
            )
        raise ValueError("MFA_LOCKED" if result.get("locked") else "MFA_INVALID")

    if not ObjectId.is_valid(result.get("user_id", "")):
        raise ValueError("MFA_INVALID")
    raw_user = await db.users.find_one({"_id": ObjectId(result["user_id"])})
    if (
        not raw_user
        or raw_user.get("role") != "admin"
        or raw_user.get("status", "active") != "active"
        or raw_user.get("is_verified") is False
    ):
        raise ValueError("MFA_INVALID")

    await user_model.reset_failed_logins(db, result["user_id"])
    return await _issue_session(
        db, raw_user, ip, "login_success", ("password", "email_otp")
    )


async def authenticate_email_otp(
    db, email: str, mode: str, name: str | None, ip: str
) -> dict:
    """Authenticate or create a customer using email OTP only."""
    email_lower = email.lower().strip()
    user = await user_model.find_by_email(db, email_lower)

    if mode == "register":
        if user:
            raise ValueError("email_conflict")
        if not name or len(name.strip()) < 2:
            raise ValueError("name_required")
        await user_model.insert_user(
            db,
            {
                "name": name.strip(),
                "email": email_lower,
                "password_hash": hash_password(secrets.token_urlsafe(32)[:32]),
                "role": "customer",
                "is_verified": True,
                "verification_status": None,
                "profile_photo_url": None,
                "addresses": [],
                "wishlist": [],
                "verification_token": None,
                "verification_token_expires": None,
            },
        )
        user = await user_model.find_by_email(db, email_lower)
        if not user:
            raise ValueError("USER_CREATE_FAILED")
        return await _issue_session(db, user, ip, "register_email_otp")

    if not user or not user.get("is_verified", False) or user.get("status", "active") != "active":
        raise ValueError("INVALID_CREDENTIALS")
    if user.get("role") == "admin":
        raise ValueError("ADMIN_MFA_REQUIRED")
    return await _issue_session(db, user, ip, "login_email_otp")


async def refresh_tokens(db, refresh_token_plain: str, ip: str = "unknown") -> dict:
    """Rotate refresh tokens and reject stale security versions."""
    from app.core.security import decode_refresh_token
    from jwt.exceptions import PyJWTError

    try:
        payload = decode_refresh_token(refresh_token_plain)
    except PyJWTError:
        raise ValueError("TOKEN_INVALID")

    user_id = payload.get("user_id")
    token_family = payload.get("token_family")
    token_hash = hash_token(refresh_token_plain)
    stored = await db.refresh_tokens.find_one({"token_hash": {"$eq": token_hash}})

    if not stored:
        await db.refresh_tokens.update_many(
            {"token_family": {"$eq": token_family}},
            {"$set": {"is_revoked": True}},
        )
        raise ValueError("TOKEN_INVALID")
    if stored.get("is_revoked"):
        raise ValueError("TOKEN_INVALID")

    await db.refresh_tokens.update_one(
        {"token_hash": {"$eq": token_hash}},
        {"$set": {"is_revoked": True}},
    )

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if (
        not user
        or user.get("status", "active") != "active"
        or user.get("is_verified") is False
        or int(user.get("auth_version", 1)) != int(stored.get("auth_version", 1))
    ):
        raise ValueError("TOKEN_INVALID")

    amr = tuple(stored.get("amr") or ("password",))
    if user.get("role") == "admin" and "email_otp" not in amr:
        raise ValueError("TOKEN_INVALID")

    session = await _issue_session(db, user, ip, "token_refresh", amr)
    return {
        "access_token": session["access_token"],
        "new_refresh_plain": session["refresh_token_plain"],
        "expires_in": session["expires_in"],
    }


async def logout_by_refresh_token(db, refresh_token_plain: str, ip: str) -> None:
    token_hash = hash_token(refresh_token_plain)
    stored = await db.refresh_tokens.find_one({"token_hash": {"$eq": token_hash}})
    if not stored:
        return
    await db.refresh_tokens.update_one(
        {"token_hash": {"$eq": token_hash}},
        {"$set": {"is_revoked": True}},
    )
    user_id = stored.get("user_id") or "unknown"
    role = "unknown"
    if stored.get("user_id"):
        user = await db.users.find_one({"_id": ObjectId(stored["user_id"])})
        if user:
            role = user.get("role", "unknown")
    await write_audit_log(
        db, user_id, role, "logout", "users", user_id, {"ip": ip}, ip
    )


async def verify_user_account(db, token_plain: str, ip: str) -> dict:
    token_hash = hash_token(token_plain)
    user = await db.users.find_one({"verification_token": {"$eq": token_hash}})
    if not user:
        raise ValueError("INVALID_TOKEN")

    expires = user.get("verification_token_expires")
    if not expires or expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("TOKEN_EXPIRED")

    user_id_str = str(user["_id"])
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"is_verified": True, "updated_at": datetime.now(timezone.utc)},
            "$unset": {"verification_token": "", "verification_token_expires": ""},
        },
    )
    await write_audit_log(
        db,
        user_id_str,
        user["role"],
        "account_verified",
        "users",
        user_id_str,
        {"ip": ip},
        ip,
    )
    return {"message": "Account successfully verified. You can now login."}
