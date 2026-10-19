"""
routers/auth_router.py
Auth endpoints — POST /register, /login, /logout, /refresh, /me, /forgot-password.
Rate limits applied via slowapi decorators on each route.
"""
import uuid
import secrets
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from bson import ObjectId
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.redis_client import store_email_otp, verify_email_otp, delete_email_otp, store_password_reset_token, consume_password_reset_token, consume_rate_limit
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.rbac_dependency import require_customer
from app.schemas.auth_schema import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    EmailOtpRequest,
    EmailOtpVerifyRequest,
    VerifyAccountRequest,
    ResetPasswordRequest,
    AdminMFAVerifyRequest,
)
from app.models import user_model
from app.services import auth_service
from app.services.audit_log_service import write_audit_log
from app.services.email_service import email_is_configured, send_email_otp, send_order_email

router  = APIRouter(prefix="/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set HttpOnly, Secure, SameSite=Strict refresh cookie."""
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth",
        max_age=7 * 24 * 3600,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth",
        max_age=0,
    )


def _success(data: dict, request_id: str | None = None) -> dict:
    return {
        "success":    True,
        "data":       data,
        "request_id": request_id or str(uuid.uuid4()),
    }


def _error(code: str, message: str, request_id: str | None = None) -> dict:
    return {
        "success":    False,
        "error":      {"code": code, "message": message},
        "request_id": request_id or str(uuid.uuid4()),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    db=Depends(get_db),
):
    try:
        await auth_service.register_user(
            db, body.name, body.email, body.password, body.role.value
        )
    except ValueError as exc:
        if "email_conflict" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_error("CONFLICT", "An account with this email already exists."),
            )
        if str(exc) in {"EMAIL_NOT_CONFIGURED", "EMAIL_DELIVERY_FAILED"}:
            raise HTTPException(
                status_code=503,
                detail=_error("EMAIL_UNAVAILABLE", "We could not send the verification email. Please try again later."),
            )
        raise
    return _success({
        "message": "Check your email and click the verification link before signing in.",
    })


@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(request: Request, body: ForgotPasswordRequest, db=Depends(get_db)):
    if not await consume_rate_limit("resend-verification", str(body.email).lower().strip(), 3, 60 * 60):
        raise HTTPException(status_code=429, detail=_error("RATE_LIMITED", "Please try again later."))
    if email_is_configured():
        try:
            await auth_service.resend_verification(db, str(body.email))
        except Exception:
            pass  # Keep account existence and email delivery state private.
    return _success({"message": "If this account needs verification, a new link has been sent."})


@router.post("/email/request-otp")
@limiter.limit("5/hour")
async def request_email_otp(
    request: Request,
    body: EmailOtpRequest,
    db=Depends(get_db),
):
    """Send a six-digit sign-in OTP only to a verified non-admin account."""
    if not email_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("EMAIL_NOT_CONFIGURED", "Email OTP is not configured yet. Add the Gmail App Password to the backend environment."),
        )
    email = str(body.email).lower().strip()
    if not await consume_rate_limit("email-otp-request", email, 5, 60 * 60):
        raise HTTPException(status_code=429, detail=_error("RATE_LIMITED", "Too many code requests. Try again later."))
    existing = await user_model.find_by_email(db, email)
    if not existing or existing.get("is_verified") is not True or existing.get("status", "active") != "active" or existing.get("role") == "admin":
        return _success({"message": "If this email has a verified account, a sign-in code has been sent.", "expires_in": settings.EMAIL_OTP_TTL_SECONDS})

    otp = str(secrets.randbelow(1_000_000)).zfill(6)
    await store_email_otp(email, otp)
    try:
        await send_email_otp(email, otp)
    except Exception as exc:
        # Do not leave a usable code behind when delivery failed.
        await delete_email_otp(email)
        if isinstance(exc, RuntimeError):
            raise HTTPException(status_code=503, detail=_error("EMAIL_NOT_CONFIGURED", str(exc)))
        raise HTTPException(status_code=502, detail=_error("EMAIL_DELIVERY_FAILED", "We could not send the code. Please try again."))
    return _success({"message": "If this email has a verified account, a sign-in code has been sent.", "expires_in": settings.EMAIL_OTP_TTL_SECONDS})


@router.post("/email/verify-otp")
@limiter.limit("15/15minute")
async def verify_email_otp_endpoint(
    request: Request,
    body: EmailOtpVerifyRequest,
    response: Response,
    db=Depends(get_db),
):
    """Verify the code and issue the regular Shoply session tokens."""
    email = str(body.email).lower().strip()
    if not await consume_rate_limit("email-otp-verify", email, settings.EMAIL_OTP_MAX_ATTEMPTS + 2, settings.EMAIL_OTP_TTL_SECONDS):
        raise HTTPException(status_code=429, detail=_error("RATE_LIMITED", "Too many verification attempts. Request a new code later."))
    result = await verify_email_otp(email, body.otp)
    if result.get("locked"):
        raise HTTPException(status_code=429, detail=_error("OTP_LOCKED", "Too many incorrect attempts. Request a new code."))
    if result.get("expired"):
        raise HTTPException(status_code=400, detail=_error("OTP_EXPIRED", "This code has expired. Request a new one."))
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=_error("OTP_INVALID", "The code is incorrect."))

    ip = request.client.host if request.client else "unknown"
    try:
        auth_result = await auth_service.authenticate_email_otp(db, email, body.mode, None, ip)
    except ValueError:
        raise HTTPException(status_code=401, detail=_error("INVALID_CREDENTIALS", "This email cannot be signed in."))

    _set_refresh_cookie(response, auth_result["refresh_token_plain"])
    return _success({
        "access_token": auth_result["access_token"],
        "token_type": "bearer",
        "expires_in": 900,
        "user": auth_result["user"],
    })


@router.post("/login")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db=Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    email_key = str(body.email).lower().strip()
    if not await consume_rate_limit("login-account", email_key, 10, 15 * 60):
        raise HTTPException(status_code=429, detail=_error("RATE_LIMITED", "Too many sign-in attempts. Try again later."))
    try:
        result = await auth_service.authenticate_user(
            db, body.email, body.password, ip
        )
    except ValueError as exc:
        code = str(exc)
        if code == "ACCOUNT_LOCKED":
            raise HTTPException(
                status_code=423,
                detail=_error("ACCOUNT_LOCKED", "Account temporarily locked. Please try again later."),
            )
        if code in {"MFA_UNAVAILABLE", "MFA_DELIVERY_FAILED"}:
            raise HTTPException(status_code=503, detail=_error("MFA_UNAVAILABLE", "Admin verification is temporarily unavailable."))
        if code == "OTP_REQUIRED":
            raise HTTPException(status_code=401, detail=_error("OTP_REQUIRED", "Use an email code to sign in."))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("INVALID_CREDENTIALS", "Invalid email or password."),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if result.get("mfa_required"):
        return _success({
            "mfa_required": True,
            "challenge_id": result["challenge_id"],
            "expires_in": result["expires_in"],
            "user": result["user"],
        })
    _set_refresh_cookie(response, result["refresh_token_plain"])
    return _success({
        "access_token": result["access_token"],
        "token_type":   "bearer",
        "expires_in":   result["expires_in"],
        "user":         result["user"],
    })


@router.post("/admin/verify-mfa")
@limiter.limit("10/15minute")
async def verify_admin_mfa(
    request: Request,
    body: AdminMFAVerifyRequest,
    response: Response,
    db=Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    if not await consume_rate_limit("admin-mfa", body.challenge_id, settings.ADMIN_MFA_MAX_ATTEMPTS + 2, settings.ADMIN_MFA_TTL_SECONDS):
        raise HTTPException(status_code=429, detail=_error("RATE_LIMITED", "Too many verification attempts. Try again later."))
    try:
        result = await auth_service.verify_admin_mfa(db, body.challenge_id, body.otp, ip)
    except ValueError as exc:
        code = str(exc)
        if code == "MFA_LOCKED":
            raise HTTPException(status_code=429, detail=_error("MFA_LOCKED", "Too many incorrect codes. Request a new login code."))
        raise HTTPException(status_code=401, detail=_error("MFA_INVALID", "The verification code is invalid or expired."))
    _set_refresh_cookie(response, result["refresh_token_plain"])
    return _success({
        "access_token": result["access_token"],
        "token_type": "bearer",
        "expires_in": result["expires_in"],
        "user": result["user"],
    })


@router.post("/refresh")
@limiter.limit("100/minute")
async def refresh(
    request: Request,
    response: Response,
    db=Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("TOKEN_INVALID", "Refresh token missing."),
        )

    try:
        result = await auth_service.refresh_tokens(db, refresh_token, request.client.host if request.client else "unknown")
    except ValueError:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("TOKEN_INVALID", "Refresh token invalid or expired."),
        )

    _set_refresh_cookie(response, result["new_refresh_plain"])

    return _success({
        "access_token": result["access_token"],
        "token_type":   "bearer",
        "expires_in":   result["expires_in"],
    })


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db=Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
):
    ip = request.client.host if request.client else "unknown"
    if refresh_token:
        await auth_service.logout_by_refresh_token(db, refresh_token, ip)
    _clear_refresh_cookie(response)
    return _success({"message": "Logged out successfully."})


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    from app.models import user_model
    user = await user_model.find_by_id(db, current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail=_error("NOT_FOUND", "User not found."))
    return _success(user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    user = await user_model.find_by_email(db, current_user["email"])
    if not user:
        raise HTTPException(status_code=404, detail=_error("NOT_FOUND", "User not found."))

    if not verify_password(body.current_password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=401,
            detail=_error("INVALID_CREDENTIALS", "Current password is incorrect."),
        )

    new_hash = hash_password(body.new_password)
    await user_model.update_user(db, current_user["user_id"], {"password_hash": new_hash}, allow_sensitive=True)
    await user_model.bump_auth_version(db, current_user["user_id"])
    await auth_service.revoke_all_sessions(db, current_user["user_id"])
    await user_model.reset_failed_logins(db, current_user["user_id"])
    await write_audit_log(
        db, current_user["user_id"], current_user["role"], "password_changed",
        "users", current_user["user_id"], {}, "local",
    )
    return _success({"message": "Password changed successfully."})


@router.post("/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db=Depends(get_db),
):
    # Always return 200 regardless of whether email exists — prevents enumeration.
    user = await user_model.find_by_email(db, str(body.email).lower().strip())
    if user and user.get("role") == "customer" and user.get("is_verified") is True and email_is_configured():
        token = secrets.token_urlsafe(36)
        await store_password_reset_token(token, str(user["_id"]), int(user.get("auth_version", 1)))
        link = f"{settings.FRONTEND_URL.rstrip('/')}/#reset_token={token}"
        try:
            await send_order_email(str(body.email), "Reset your Shoply password", f"Use this link within 30 minutes to reset your password:\n{link}")
        except Exception:
            pass
    return _success({"message": "If that email exists, a reset link has been sent."})


@router.post("/reset-password")
@limiter.limit("5/hour")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db=Depends(get_db),
):
    reset_claim = await consume_password_reset_token(body.token)
    if not reset_claim:
        raise HTTPException(status_code=400, detail=_error("RESET_TOKEN_INVALID", "This reset link is invalid or expired."))
    user_id = reset_claim["user_id"]
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail=_error("RESET_TOKEN_INVALID", "This reset link is invalid or expired."))
    from pymongo import ReturnDocument
    user = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id), "role": "customer", "is_verified": True,
         "status": {"$in": ["active", None]}, "auth_version": reset_claim["auth_version"]},
        {"$set": {"password_hash": hash_password(body.new_password)}, "$inc": {"auth_version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not user:
        raise HTTPException(status_code=400, detail=_error("RESET_TOKEN_INVALID", "This reset link is invalid or expired."))
    await auth_service.revoke_all_sessions(db, user_id)
    await user_model.reset_failed_logins(db, user_id)
    await write_audit_log(db, user_id, user.get("role", "customer"), "password_reset", "users", user_id, {}, request.client.host if request.client else "unknown")
    return _success({"message": "Password reset successfully. You can sign in now."})


@router.post("/verify", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")
async def verify_account(
    request: Request,
    body: VerifyAccountRequest,
    db=Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    
    try:
        result = await auth_service.verify_user_account(db, body.token, ip)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error("INVALID_TOKEN", "This verification link is invalid or expired."),
        )

    return _success(result)
