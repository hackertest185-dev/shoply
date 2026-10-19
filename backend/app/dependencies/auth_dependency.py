"""
dependencies/auth_dependency.py
FastAPI dependency: decodes JWT Bearer token, returns current_user dict.
Raises HTTP 401 on failure. Injected into every protected route.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_db
from app.core.security import decode_access_token
from jwt.exceptions import PyJWTError
from bson import ObjectId

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db=Depends(get_db),
) -> dict:
    """
    Decode and validate JWT. Checks:
    1. Token present in Authorization header
    2. RS256 signature valid
    3. Token not expired
    Returns dict: { user_id, email, role, jti }
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "Authorization token required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except PyJWTError as exc:
        code = "TOKEN_EXPIRED" if "expired" in str(exc).lower() else "TOKEN_INVALID"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": code, "message": "Invalid or expired token."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "Token payload malformed."},
        )

    user = await db.users.find_one(
        {"_id": ObjectId(user_id)},
        {"email": 1, "role": 1, "status": 1, "is_verified": 1, "auth_version": 1},
    )
    if not user or user.get("status", "active") != "active" or user.get("is_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "Account is unavailable."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token_version = int(payload.get("auth_version", 1))
        user_version = int(user.get("auth_version", 1))
    except (TypeError, ValueError):
        token_version = user_version = -1
    if token_version != user_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "Session is no longer valid."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    amr = payload.get("amr") or []
    if "email_otp" not in amr or (user.get("role") == "admin" and "password" not in amr):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MFA_REQUIRED", "message": "An email-code session is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": user_id,
        "email": user.get("email"),
        "role": user.get("role"),
        "jti": payload.get("jti"),
        "auth_version": int(user.get("auth_version", 1)),
        "amr": payload.get("amr") or [],
    }
