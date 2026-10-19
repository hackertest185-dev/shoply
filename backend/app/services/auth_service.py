"""
services/auth_service.py
All authentication business logic. No HTTP concepts — pure Python.
"""
import secrets
from datetime import datetime, timedelta, timezone

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


MAX_FAILED_LOGINS = 10
LOCKOUT_MINUTES = 30


async def _issue_session(db, user: dict, ip: str, event: str = "login_success") -> dict:
    """Issue the same access/refresh pair for password and email-OTP auth."""
    user_id_str = str(user["_id"])
    token_family = secrets.token_hex(16)
    access_token = create_access_token({
        "user_id": user_id_str,
        "email": user["email"],
        "role": user["role"],
    })
    refresh_plaintext, refresh_hash = create_refresh_token(user_id_str, token_family)
    await db.refresh_tokens.insert_one({
        "user_id": user_id_str,
        "token_hash": refresh_hash,
        "token_family": token_family,
        "is_revoked": False,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    })
    safe_user = {
        "id": user_id_str,
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "verification_status": user.get("verification_status"),
    }
    await write_audit_log(
        db, user_id_str, user["role"], event,
        "users", user_id_str, {"ip": ip, "method": "email_otp"}, ip,
    )
    return {
        "access_token": access_token,
        "refresh_token_plain": refresh_plaintext,
        "user": safe_user,
    }


async def register_user(db, name: str, email: str, password: str, role: str) -> dict:
    """
    Register a new user account.
    Returns dict with user_id and verification_token (plaintext — email it, don't store).
    Raises ValueError on duplicate email.
    """
    email_lower = email.lower().strip()

    # Check duplicate — use same error message regardless to prevent enumeration
    existing = await user_model.find_by_email(db, email_lower)
    if existing:
        raise ValueError("email_conflict")  # caller maps to 409

    pwd_hash = hash_password(password)

    # Local dev: accounts are auto-verified since there is no email service yet.
    # The email-verification flow can be wired later when SendGrid is integrated.
    user_data = {
        "name":                name.strip(),
        "email":               email_lower,
        "password_hash":       pwd_hash,
        "role":                role,
        "is_verified":         True,
        "verification_status": None,
        "profile_photo_url":   None,
        "addresses":           [],
        "wishlist":            [],
        "verification_token":  None,
        "verification_token_expires": None,
    }

    user_id = await user_model.insert_user(db, user_data)
    return {"user_id": user_id}


async def authenticate_user(
    db, email: str, password: str, ip: str
) -> dict:
    """
    Authenticate with email + password.
    Returns { access_token, refresh_token_plaintext, user }.
    Raises ValueError with code on failure.
    Always runs bcrypt even when user not found (timing equalization).
    """
    email_lower = email.lower().strip()
    user = await user_model.find_by_email(db, email_lower)

    if not user:
        # Run bcrypt against dummy hash to equalize timing
        verify_password(password, DUMMY_HASH)
        raise ValueError("INVALID_CREDENTIALS")

    # Check account lock
    locked_until = user.get("account_locked_until")
    if locked_until and locked_until > datetime.now(timezone.utc):
        raise ValueError("ACCOUNT_LOCKED")

    is_valid = verify_password(password, user.get("password_hash", ""))

    if not is_valid:
        count = await user_model.increment_failed_logins(db, str(user["_id"]))
        if count >= MAX_FAILED_LOGINS:
            lock_time = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            await user_model.update_user(
                db, str(user["_id"]), {"account_locked_until": lock_time}
            )
        await write_audit_log(
            db, str(user["_id"]), user["role"], "login_failure",
            "users", str(user["_id"]), {"ip": ip}, ip,
        )
        raise ValueError("INVALID_CREDENTIALS")

    if not user.get("is_verified") or user.get("status", "active") != "active":
        raise ValueError("INVALID_CREDENTIALS")  # Same message — no account status disclosure

    # Reset failed logins
    await user_model.reset_failed_logins(db, str(user["_id"]))

    # Issue tokens
    user_id_str = str(user["_id"])
    token_family = secrets.token_hex(16)

    access_token = create_access_token({
        "user_id": user_id_str,
        "email":   user["email"],
        "role":    user["role"],
    })
    refresh_plaintext, refresh_hash = create_refresh_token(user_id_str, token_family)

    # Store hashed refresh token
    await db.refresh_tokens.insert_one({
        "user_id":      user_id_str,
        "token_hash":   refresh_hash,
        "token_family": token_family,
        "is_revoked":   False,
        "expires_at":   datetime.now(timezone.utc) + timedelta(days=7),
    })

    safe_user = {
        "id":                  user_id_str,
        "name":                user["name"],
        "email":               user["email"],
        "role":                user["role"],
        "verification_status": user.get("verification_status"),
    }

    await write_audit_log(
        db, user_id_str, user["role"], "login_success",
        "users", user_id_str, {"ip": ip}, ip,
    )

    return {
        "access_token":          access_token,
        "refresh_token_plain":   refresh_plaintext,
        "user":                  safe_user,
    }


async def authenticate_email_otp(
    db, email: str, mode: str, name: str | None, ip: str
) -> dict:
    """Authenticate an existing user or create a customer after email OTP."""
    email_lower = email.lower().strip()
    user = await user_model.find_by_email(db, email_lower)

    if mode == "register":
        if user:
            raise ValueError("email_conflict")
        if not name or len(name.strip()) < 2:
            raise ValueError("name_required")
        user_data = {
            "name": name.strip(),
            "email": email_lower,
            # OTP is the credential for this flow; password login remains available
            # for the provisioned admin account.
            "password_hash": hash_password(secrets.token_urlsafe(32)[:32]),
            "role": "customer",
            "is_verified": True,
            "verification_status": None,
            "profile_photo_url": None,
            "addresses": [],
            "wishlist": [],
            "verification_token": None,
            "verification_token_expires": None,
        }
        user_id = await user_model.insert_user(db, user_data)
        user = await user_model.find_by_email(db, email_lower)
        if not user:
            raise ValueError("USER_CREATE_FAILED")
        result = await _issue_session(db, user, ip, "register_email_otp")
        result["user_id"] = user_id
        return result

    if not user or not user.get("is_verified", False) or user.get("status", "active") != "active":
        raise ValueError("INVALID_CREDENTIALS")
    return await _issue_session(db, user, ip, "login_email_otp")


async def refresh_tokens(db, refresh_token_plain: str) -> dict:
    """
    Rotate refresh token. Detects reuse via token family.
    Returns { access_token, new_refresh_token_plain }.
    Raises ValueError on invalid/expired/reused token.
    """
    from app.core.security import decode_refresh_token
    from jwt.exceptions import PyJWTError

    try:
        payload = decode_refresh_token(refresh_token_plain)
    except PyJWTError:
        raise ValueError("TOKEN_INVALID")

    user_id     = payload.get("user_id")
    token_family = payload.get("token_family")
    token_hash  = hash_token(refresh_token_plain)

    stored = await db.refresh_tokens.find_one({"token_hash": {"$eq": token_hash}})

    if not stored:
        # Token hash not found — could be a reuse attack. Revoke entire family.
        await db.refresh_tokens.update_many(
            {"token_family": {"$eq": token_family}},
            {"$set": {"is_revoked": True}},
        )
        raise ValueError("TOKEN_INVALID")

    if stored.get("is_revoked"):
        raise ValueError("TOKEN_INVALID")

    # Revoke old token
    await db.refresh_tokens.update_one(
        {"token_hash": {"$eq": token_hash}},
        {"$set": {"is_revoked": True}},
    )

    # Fetch user
    user = await user_model.find_by_id(db, user_id)
    if not user or user.get("status", "active") != "active" or user.get("is_verified") is False:
        raise ValueError("TOKEN_INVALID")

    # Issue new pair
    access_token = create_access_token({
        "user_id": user_id,
        "email":   user["email"],
        "role":    user["role"],
    })
    new_refresh_plain, new_refresh_hash = create_refresh_token(user_id, token_family)

    await db.refresh_tokens.insert_one({
        "user_id":      user_id,
        "token_hash":   new_refresh_hash,
        "token_family": token_family,
        "is_revoked":   False,
        "expires_at":   datetime.now(timezone.utc) + timedelta(days=7),
    })

    return {"access_token": access_token, "new_refresh_plain": new_refresh_plain}


async def logout_user(db, user_id: str, refresh_token_plain: str, ip: str) -> None:
    """Revoke refresh token. Write audit log."""
    token_hash = hash_token(refresh_token_plain)
    await db.refresh_tokens.update_one(
        {"token_hash": {"$eq": token_hash}},
        {"$set": {"is_revoked": True}},
    )
    await write_audit_log(
        db, user_id, "unknown", "logout", "users", user_id, {"ip": ip}, ip,
    )


async def logout_by_refresh_token(db, refresh_token_plain: str, ip: str) -> None:
    """
    Revoke refresh token session even when access token is missing/expired.
    This lets clients fully terminate session cookie state on logout.
    """
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
        user = await user_model.find_by_id(db, stored["user_id"])
        if user:
            role = user.get("role", "unknown")

    await write_audit_log(
        db, user_id, role, "logout", "users", user_id, {"ip": ip}, ip,
    )



async def verify_user_account(db, token_plain: str, ip: str) -> dict:
    """
    Verify user account using the plaintext token.
    Hashes the token and compares with DB.
    Raises ValueError on invalid or expired token.
    """
    # 1. تشفير التوكن القادم من المستخدم لمطابقته مع المخزن في الداتا بيز
    token_hash = hash_token(token_plain)
    
    # 2. البحث عن المستخدم باستخدام التوكن المشفر
    user = await db.users.find_one({"verification_token": {"$eq": token_hash}})
    
    if not user:
        raise ValueError("INVALID_TOKEN")
        
    # 3. التأكد من صلاحية التوكن (أنه لم ينتهِ وقته)
    expires = user.get("verification_token_expires")
    if not expires or expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("TOKEN_EXPIRED")
        
    # 4. تحديث حالة الحساب وحرق التوكن
    user_id_str = str(user["_id"])
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "is_verified": True,
                "updated_at": datetime.now(timezone.utc)
            },
            "$unset": {
                "verification_token": "",
                "verification_token_expires": ""
            }
        }
    )
    
    # 5. تسجيل العملية في سجلات التدقيق (Audit Log) لأغراض الحماية
    await write_audit_log(
        db, user_id_str, user["role"], "account_verified",
        "users", user_id_str, {"ip": ip}, ip,
    )
    
    return {"message": "Account successfully verified. You can now login."}
