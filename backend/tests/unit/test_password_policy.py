import pytest
from pydantic import ValidationError

from app.schemas.auth_schema import (
    ChangePasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest,
)


def requests_for(password):
    return [
        (RegisterRequest, {"name": "Buyer", "email": "buyer@example.com", "password": password}),
        (ResetPasswordRequest, {"token": "t" * 36, "new_password": password}),
        (ChangePasswordRequest, {"current_password": "legacy-password", "new_password": password}),
    ]


@pytest.mark.parametrize("password", [
    "Short1!", "lowercase123!", "UPPERCASE123!", "NoNumbersHere!",
    "NoSymbolHere123", "Password123!", "Welcome12345#",
    " GoodPassword123!", "GoodPassword123! ", "GoodPass1!" + "ق" * 35,
])
def test_all_new_password_endpoints_reject_weak_or_unsafe_passwords(password):
    for schema, fields in requests_for(password):
        with pytest.raises(ValidationError):
            schema(**fields)


@pytest.mark.parametrize("password", ["MapleRiver9@", "Copper!Meadow#82", "GoodPass1!" + "ق" * 20])
def test_all_new_password_endpoints_accept_strong_passwords(password):
    for schema, fields in requests_for(password):
        schema(**fields)


def test_existing_passwords_can_still_reach_login():
    assert LoginRequest(email="buyer@example.com", password="old-password").password == "old-password"
