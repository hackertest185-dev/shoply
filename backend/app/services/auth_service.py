"""
services/auth_service.py
All authentication business logic. No HTTP concepts - pure Python.
"""
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.redis_client import (
    delete_login_challenge,
    store_login_challenge,
    verify_login_challenge,
)
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    generate_secure_token,
    verify_password,
)
from app.models import user_model
from app.services.audit_log_service import write_audit_log
from app.services.email_service import email_is_configured, send_email_otp, send_verification_email


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
    """Create an unverified customer and email a one-time, account-bound link."""
    if role != "customer":
        raise ValueError("invalid_registration_role")
    if not email_is_configured():
        raise ValueError("EMAIL_NOT_CONFIGURED")
    email_lower = email.lower().strip()
    if await user_model.find_by_email(db, email_lower):
        raise ValueError("email_conflict")
    token_plain, token_hash = generate_secure_token()
    try:
        user_id = await user_model.insert_user(db, {
            "name": name.strip(),
            "email": email_lower,
            "password_hash": hash_password(password),
            "role": "customer",
            "is_verified": False,
            "verification_status": None,
            "profile_photo_url": None,
            "addresses": [],
            "wishlist": [],
            "verification_token": token_hash,
            "verification_token_expires": datetime.now(timezone.utc) + timedelta(seconds=settings.EMAIL_VERIFICATION_TTL_SECONDS),
        })
    except DuplicateKeyError as exc:
        raise ValueError("email_conflict") from exc

    link = f"{settings.FRONTEND_URL.rstrip('/')}/#verify_token={token_plain}"
    try:
        await send_verification_email(email_lower, link)
    except Exception as exc:
        # A failed delivery must not leave a newly registered address unusable.
        await db.users.delete_one({"_id": ObjectId(user_id), "verification_token": token_hash, "is_verified": False})
        raise ValueError("EMAIL_DELIVERY_FAILED") from exc
    return {"user_id": user_id}


async def resend_verification(db, email: str) -> None:
    """Rotate the link for a pending customer without disclosing account state."""
    email_lower = email.lower().strip()
    current = await db.users.find_one(
        {"email": {"$eq": email_lower}, "role": "customer", "is_verified": False,
         "status": {"$in": ["active", None]}},
    )
    if not current:
        return
    token_plain, token_hash = generate_secure_token()
    result = await db.users.update_one(
        {"_id": current["_id"], "is_verified": False,
         "verification_token": current.get("verification_token")},
        {"$set": {
            "verification_token": token_hash,
            "verification_token_expires": datetime.now(timezone.utc) + timedelta(seconds=settings.EMAIL_VERIFICATION_TTL_SECONDS),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    if result.matched_count:
        link = f"{settings.FRONTEND_URL.rstrip('/')}/#verify_token={token_plain}"
        try:
            await send_verification_email(email_lower, link)
        except Exception:
            restore = {"verification_token": current.get("verification_token"),
                       "verification_token_expires": current.get("verification_token_expires")}
            await db.users.update_one(
                {"_id": current["_id"], "verification_token": token_hash, "is_verified": False},
                {"$set": restore},
            )
            raise


async def authenticate_user(db, email: str, password: str, ip: str) -> dict:
    """Authenticate with a password; every account then requires an email code."""
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

    if user.get("is_verified") is not True:
        raise ValueError("EMAIL_NOT_VERIFIED")
    if user.get("status", "active") != "active":
        raise ValueError("INVALID_CREDENTIALS")

    await user_model.reset_failed_logins(db, str(user["_id"]))

    if not email_is_configured():
        raise ValueError("MFA_UNAVAILABLE")

    challenge_id = secrets.token_urlsafe(32)
    otp = str(secrets.randbelow(1_000_000)).zfill(6)
    await store_login_challenge(
        challenge_id,
        str(user["_id"]),
        int(user.get("auth_version", 1)),
        otp,
        settings.LOGIN_OTP_TTL_SECONDS,
    )
    try:
        await send_email_otp(user["email"], otp)
    except Exception as exc:
        await delete_login_challenge(challenge_id)
        await write_audit_log(
            db, str(user["_id"]), user["role"], "login_otp_delivery_failed",
            "users", str(user["_id"]), {"ip": ip}, ip,
        )
        raise ValueError("MFA_DELIVERY_FAILED") from exc

    await write_audit_log(
        db, str(user["_id"]), user["role"], "login_otp_requested",
        "users", str(user["_id"]), {"ip": ip}, ip,
    )
    return {
        "mfa_required": True,
        "challenge_id": challenge_id,
        "expires_in": settings.LOGIN_OTP_TTL_SECONDS,
        "user": {"email": user["email"]},
    }


async def verify_login_otp(db, challenge_id: str, otp: str, ip: str) -> dict:
    """Issue a session only for the account whose password created this challenge."""
    result = await verify_login_challenge(
        challenge_id, otp, settings.LOGIN_OTP_MAX_ATTEMPTS,
        settings.LOGIN_OTP_TTL_SECONDS,
    )
    if not result.get("valid"):
        event = "login_otp_locked" if result.get("locked") else "login_otp_failure"
        if result.get("user_id"):
            await write_audit_log(
                db,
                result["user_id"],
                "unknown",
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
        or raw_user.get("status", "active") != "active"
        or raw_user.get("is_verified") is not True
        or int(raw_user.get("auth_version", 1)) != result["auth_version"]
    ):
        raise ValueError("MFA_INVALID")

    await user_model.reset_failed_logins(db, result["user_id"])
    return await _issue_session(
        db, raw_user, ip, "login_success", ("password", "email_otp")
    )


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
        if isinstance(token_family, str) and token_family:
            await db.refresh_tokens.update_many(
                {"token_family": {"$eq": token_family}},
                {"$set": {"is_revoked": True}},
            )
        raise ValueError("TOKEN_INVALID")
    if stored.get("is_revoked"):
        # Reuse of a consumed token revokes every descendant in the family.
        stored_family = stored.get("token_family")
        if isinstance(stored_family, str) and stored_family:
            await db.refresh_tokens.update_many(
                {"token_family": {"$eq": stored_family}},
                {"$set": {"is_revoked": True}},
            )
        raise ValueError("TOKEN_INVALID")
    if (
        stored.get("user_id") != user_id
        or stored.get("token_family") != token_family
        or not isinstance(user_id, str)
        or not isinstance(token_family, str)
    ):
        raise ValueError("TOKEN_INVALID")

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if (
        not user
        or user.get("status", "active") != "active"
        or user.get("is_verified") is not True
        or int(user.get("auth_version", 1)) != int(stored.get("auth_version", 1))
    ):
        raise ValueError("TOKEN_INVALID")

    amr = tuple(stored.get("amr") or ("password",))
    if "email_otp" not in amr or "password" not in amr:
        raise ValueError("TOKEN_INVALID")

    # Consume the token atomically. Parallel refreshes must not both mint a
    # fresh session from the same bearer cookie.
    consumed = await db.refresh_tokens.find_one_and_update(
        {"token_hash": {"$eq": token_hash}, "is_revoked": False},
        {"$set": {"is_revoked": True}},
        return_document=ReturnDocument.BEFORE,
    )
    if not consumed:
        stored_family = stored.get("token_family")
        if isinstance(stored_family, str) and stored_family:
            await db.refresh_tokens.update_many(
                {"token_family": {"$eq": stored_family}},
                {"$set": {"is_revoked": True}},
            )
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
    """Consume only the matching unexpired verification token, atomically."""
    token_hash = hash_token(token_plain)
    now = datetime.now(timezone.utc)
    user = await db.users.find_one_and_update(
        {
            "verification_token": {"$eq": token_hash},
            "verification_token_expires": {"$gt": now},
            "role": "customer",
            "is_verified": False,
        },
        {"$set": {"is_verified": True, "updated_at": now},
         "$unset": {"verification_token": "", "verification_token_expires": ""}},
        return_document=ReturnDocument.AFTER,
    )
    if not user:
        raise ValueError("INVALID_TOKEN")
    user_id_str = str(user["_id"])
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
