"""
schemas/auth_schema.py
Pydantic v2 request/response models for all auth endpoints.
ConfigDict(extra="forbid") on all request schemas — extra fields rejected.
"""
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRole(str, Enum):
    CUSTOMER = "customer"
    # Admin accounts are provisioned separately; public signup creates customers only.


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:     str      = Field(..., min_length=2, max_length=100)
    email:    EmailStr = Field(..., max_length=254)
    password: str      = Field(..., min_length=8, max_length=72)
    role:     UserRole = UserRole.CUSTOMER

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        # Basic complexity — no spaces, mixed requirements are UX trade-off
        if v.strip() != v:
            raise ValueError("Password cannot start or end with spaces")
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email:    EmailStr
    password: str = Field(..., max_length=72)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class EmailOtpRequest(BaseModel):
    """Request a one-time sign-in or account-creation code by email."""
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    mode: Literal["login", "register"] = "login"
    name: str | None = Field(default=None, min_length=2, max_length=100)


class EmailOtpVerifyRequest(BaseModel):
    """Verify an email OTP and create a session."""
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    otp: str = Field(..., pattern=r"^[0-9]{6}$")
    mode: Literal["login", "register"] = "login"
    name: str | None = Field(default=None, min_length=2, max_length=100)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(..., min_length=8, max_length=72)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(..., max_length=72)
    new_password:     str = Field(..., min_length=8, max_length=72)


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
    token: str = Field(..., description="The plaintext verification token from the email")
