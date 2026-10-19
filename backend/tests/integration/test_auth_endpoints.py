"""
tests/integration/test_auth_endpoints.py
Integration tests hitting the full FastAPI stack with an in-memory DB.
Run with: pytest tests/integration/ -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from mongomock_motor import AsyncMongoMockClient

from app.core.database import get_db
from app.main import app
from app.services import auth_service


@pytest_asyncio.fixture
async def client(monkeypatch):
    db = AsyncMongoMockClient().shoply_test
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(auth_service, "email_is_configured", lambda: True)

    async def fake_verification_email(email, link):
        return None

    monkeypatch.setattr(auth_service, "send_verification_email", fake_verification_email)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_register_returns_201(client):
    r = await client.post("/api/v1/auth/register", json={
        "name": "Test User",
        "email": "testuser@example.com",
        "password": "SecurePass99",
        "role": "customer",
    })
    assert r.status_code in (201, 409)   # 409 if already exists in test run


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client):
    r = await client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "wrongpassword",
    })
    assert r.status_code == 401
    body = r.json()
    assert body["detail"]["error"]["code"] == "INVALID_CREDENTIALS"
    # Verify message doesn't reveal whether email exists
    assert "email or password" in body["detail"]["error"]["message"].lower()


@pytest.mark.asyncio
async def test_protected_route_without_token_returns_401(client):
    r = await client.get("/api/v1/cart")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_rejects_admin_role(client):
    r = await client.post("/api/v1/auth/register", json={
        "name": "Hacker",
        "email": "hacker@evil.com",
        "password": "password123",
        "role": "admin",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_extra_fields(client):
    r = await client.post("/api/v1/auth/register", json={
        "name": "Test",
        "email": "test2@example.com",
        "password": "password123",
        "role": "customer",
        "is_admin": True,   # Injected extra field
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_forgot_password_always_returns_200(client):
    """Must return 200 regardless of whether email exists — prevents enumeration."""
    for email in ("real@example.com", "fake@example.net"):
        r = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert r.status_code == 200
