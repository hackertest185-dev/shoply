"""
schemas/auth_schema.py
Pydantic v2 request/response models for all auth endpoints.
ConfigDict(extra="forbid") on all request schemas — extra fields rejected.
"""
from enum import Enum
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.core.config import settings


_COMMON_PASSWORDS = {
    "passwordpassword", "password1234", "123456789012", "qwertyuiop12",
    "letmein123456", "adminadmin1234", "welcome123456",
}


def _validate_password(value: str) -> str:
    if value.strip() != value:
        raise ValueError("Password cannot start or end with spaces")
    if len(value) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    if value.lower() in _COMMON_PASSWORDS:
        raise ValueError("Choose a less common password")
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise ValueError("Password must contain letters and numbers")
    return value


class UserRole(str, Enum):
    CUSTOMER = "customer"
    # Admin accounts are provisioned separately; public signup creates customers only.


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:     str      = Field(..., min_length=2, max_length=100)
    email:    EmailStr = Field(..., max_length=254)
    password: str      = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=72)
    role:     UserRole = UserRole.CUSTOMER

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password(v)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email:    EmailStr
    password: str = Field(..., max_length=72)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., min_length=20, max_length=256)
    new_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=72)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password(v)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(..., max_length=72)
    new_password:     str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=72)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password(v)


class LoginOtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(..., min_length=32, max_length=256)
    otp: str = Field(..., pattern=r"^[0-9]{6}$")


# ── Response models ───────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id:                  str
    name:                str
    email:               str
    role:                str
    is_verified:         bool
    verification_status: str | None
    profile_photo_url:   str | None
    created_at:          str


class LoginResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int = 900
    user:         UserResponse


class VerifyAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., min_length=32, max_length=256, description="The one-time token from the verification email")
