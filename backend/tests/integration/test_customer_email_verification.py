"""Customer email ownership and account-bound recovery regression tests."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core import redis_client
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.main import app
from app.routers import auth_router
from app.services import auth_service


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None):
        self.values[key] = str(value)

    async def get(self, key):
        return self.values.get(key)

    async def getdel(self, key):
        return self.values.pop(key, None)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)

    async def exists(self, key):
        return int(key in self.values)

    async def incr(self, key):
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key, seconds):
        return int(key in self.values)


@pytest_asyncio.fixture
async def auth_setup(monkeypatch):
    db = AsyncMongoMockClient().shoply_test
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(auth_router.limiter, "enabled", False)
    fake_redis = MemoryRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(auth_service, "email_is_configured", lambda: True)
    monkeypatch.setattr(auth_router, "email_is_configured", lambda: True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, "JWT_PRIVATE_KEY", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode())
    monkeypatch.setattr(settings, "JWT_PUBLIC_KEY", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode())

    sent = {"verify": [], "otp": [], "reset": []}

    async def capture_verification(email, link):
        sent["verify"].append((email, link))

    async def capture_otp(email, code):
        sent["otp"].append((email, code))

    async def capture_reset(email, subject, body):
        sent["reset"].append((email, body))

    monkeypatch.setattr(auth_service, "send_verification_email", capture_verification)
    monkeypatch.setattr(auth_router, "send_email_otp", capture_otp)
    monkeypatch.setattr(auth_router, "send_order_email", capture_reset)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db, sent
    finally:
        app.dependency_overrides.clear()


def token_from_link(link, field):
    return parse_qs(urlparse(link).fragment)[field][0]


async def register(client, email, password="SecurePassword123"):
    return await client.post("/api/v1/auth/register", json={
        "name": "Test Buyer", "email": email, "password": password,
    })


@pytest.mark.asyncio
async def test_verification_link_is_required_one_time_and_account_bound(auth_setup):
    client, db, sent = auth_setup
    a, b = "buyer-a@example.com", "buyer-b@example.com"
    assert (await register(client, a)).status_code == 201
    assert (await register(client, b)).status_code == 201
    user_a = await db.users.find_one({"email": a})
    user_b = await db.users.find_one({"email": b})
    assert user_a["is_verified"] is False
    assert user_b["is_verified"] is False

    # Browser response tampering cannot change the persisted account state.
    forged_claim = create_access_token({
        "user_id": str(user_a["_id"]), "email": a, "role": "customer",
        "is_verified": True, "auth_version": 1, "amr": ["email_otp"],
    })
    denied = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged_claim}"})
    assert denied.status_code == 401
    password_login = await client.post("/api/v1/auth/login", json={
        "email": a, "password": "SecurePassword123",
    })
    assert password_login.status_code == 401
    assert "access_token" not in password_login.text
    assert (await client.post("/api/v1/auth/email/request-otp", json={"email": a})).status_code == 200
    assert sent["otp"] == []

    token_a = token_from_link(sent["verify"][0][1], "verify_token")
    assert token_a not in str(user_a)
    assert (await client.post("/api/v1/auth/verify", json={"token": token_a})).status_code == 200
    assert (await db.users.find_one({"_id": user_a["_id"]}))["is_verified"] is True
    assert (await db.users.find_one({"_id": user_b["_id"]}))["is_verified"] is False
    assert (await client.post("/api/v1/auth/verify", json={"token": token_a})).status_code == 400
    assert (await client.post("/api/v1/auth/email/request-otp", json={"email": b})).status_code == 200
    assert sent["otp"] == []

    injected = await client.post("/api/v1/auth/register", json={
        "name": "Injected", "email": "evil@example.com",
        "password": "SecurePassword123", "is_verified": True,
    })
    assert injected.status_code == 422
    register_mode = await client.post("/api/v1/auth/email/request-otp", json={
        "email": "new@example.com", "mode": "register",
    })
    assert register_mode.status_code == 422

    assert (await client.post("/api/v1/auth/email/request-otp", json={"email": a})).status_code == 200
    code_a = sent["otp"][-1][1]
    wrong_account = await client.post("/api/v1/auth/email/verify-otp", json={
        "email": b, "otp": code_a,
    })
    assert wrong_account.status_code == 400
    signed_in = await client.post("/api/v1/auth/email/verify-otp", json={
        "email": a, "otp": code_a,
    })
    assert signed_in.status_code == 200
    assert signed_in.json()["data"]["user"]["email"] == a
    access_token = signed_in.json()["data"]["access_token"]
    own_profile = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {access_token}",
    })
    assert own_profile.status_code == 200
    assert own_profile.json()["data"]["email"] == a
    replay = await client.post("/api/v1/auth/email/verify-otp", json={
        "email": a, "otp": code_a,
    })
    assert replay.status_code == 400
    assert (await client.post("/api/v1/auth/login", json={
        "email": a, "password": "SecurePassword123",
    })).status_code == 401


@pytest.mark.asyncio
async def test_reset_link_cannot_be_swapped_to_another_account(auth_setup):
    client, db, sent = auth_setup
    a, b = "reset-a@example.com", "reset-b@example.com"
    assert (await register(client, a)).status_code == 201
    assert (await register(client, b)).status_code == 201
    for _, link in sent["verify"]:
        token = token_from_link(link, "verify_token")
        assert (await client.post("/api/v1/auth/verify", json={"token": token})).status_code == 200

    original_b = (await db.users.find_one({"email": b}))["password_hash"]
    assert (await client.post("/api/v1/auth/forgot-password", json={"email": a})).status_code == 200
    reset_token = token_from_link(sent["reset"][-1][1].splitlines()[-1], "reset_token")
    swapped = await client.post("/api/v1/auth/reset-password", json={
        "token": reset_token, "new_password": "DifferentPassword123", "email": b,
    })
    assert swapped.status_code == 422
    completed = await client.post("/api/v1/auth/reset-password", json={
        "token": reset_token, "new_password": "DifferentPassword123",
    })
    assert completed.status_code == 200
    assert verify_password("DifferentPassword123", (await db.users.find_one({"email": a}))["password_hash"])
    assert (await db.users.find_one({"email": b}))["password_hash"] == original_b
    replay = await client.post("/api/v1/auth/reset-password", json={
        "token": reset_token, "new_password": "AnotherPassword123",
    })
    assert replay.status_code == 400

    await client.post("/api/v1/auth/forgot-password", json={"email": a})
    stale = token_from_link(sent["reset"][-1][1].splitlines()[-1], "reset_token")
    user_a = await db.users.find_one({"email": a})
    await db.users.update_one({"_id": user_a["_id"]}, {"$inc": {"auth_version": 1}})
    assert (await client.post("/api/v1/auth/reset-password", json={
        "token": stale, "new_password": "AnotherPassword123",
    })).status_code == 400


@pytest.mark.asyncio
async def test_expired_link_needs_a_new_verification_email(auth_setup):
    client, db, sent = auth_setup
    email = "pending@example.com"
    assert (await register(client, email)).status_code == 201
    old_token = token_from_link(sent["verify"][-1][1], "verify_token")
    await db.users.update_one({"email": email}, {"$set": {
        "verification_token_expires": datetime.now(timezone.utc) - timedelta(seconds=1),
    }})
    assert (await client.post("/api/v1/auth/verify", json={"token": old_token})).status_code == 400
    response = await client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert response.status_code == 200
    new_token = token_from_link(sent["verify"][-1][1], "verify_token")
    assert new_token != old_token
    assert (await client.post("/api/v1/auth/verify", json={"token": old_token})).status_code == 400
    assert (await client.post("/api/v1/auth/verify", json={"token": new_token})).status_code == 200
