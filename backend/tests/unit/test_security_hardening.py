import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas.auth_schema import LoginOtpVerifyRequest, ChangePasswordRequest, RegisterRequest


def test_login_otp_schema_requires_six_digit_code():
    with pytest.raises(ValidationError):
        LoginOtpVerifyRequest(challenge_id="a" * 32, otp="123")


def test_password_changes_require_twelve_characters():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old-password", new_password="short123")


def test_public_registration_cannot_create_admin():
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Attacker",
            email="attacker@example.com",
            password="StrongPassword123",
            role="admin",
        )


def test_admin_user_mutation_route_is_removed():
    paths = set()
    def collect(routes):
        for route in routes:
            if hasattr(route, "path"):
                paths.add(route.path)
            if hasattr(route, "routes"):
                collect(route.routes)
    collect(app.routes)
    assert "/api/v1/admin/users/{user_id}" not in paths
