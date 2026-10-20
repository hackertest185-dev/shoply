"""A signed token cannot override the current account role or status."""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from mongomock_motor import AsyncMongoMockClient

from app.dependencies import auth_dependency


@pytest.mark.asyncio
async def test_current_role_comes_from_database_and_suspension_revokes_access(monkeypatch):
    db = AsyncMongoMockClient().shoply_test
    user_id = ObjectId()
    await db.users.insert_one({
        "_id": user_id, "email": "buyer@example.com", "role": "customer",
        "status": "active", "is_verified": True,
    })
    monkeypatch.setattr(auth_dependency, "decode_access_token", lambda _: {
        "user_id": str(user_id), "email": "buyer@example.com", "role": "admin", "jti": "old-role",
        "amr": ["password", "email_otp"],
    })
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")

    identity = await auth_dependency.get_current_user(credential, db)
    assert identity["role"] == "customer"

    await db.users.update_one({"_id": user_id}, {"$set": {"status": "suspended"}})
    with pytest.raises(HTTPException) as error:
        await auth_dependency.get_current_user(credential, db)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_unverified_and_password_only_customer_tokens_are_rejected(monkeypatch):
    db = AsyncMongoMockClient().shoply_test
    user_id = ObjectId()
    await db.users.insert_one({
        "_id": user_id, "email": "buyer@example.com", "role": "customer",
        "status": "active", "is_verified": False, "auth_version": 1,
    })
    payload = {
        "user_id": str(user_id), "email": "buyer@example.com", "role": "customer",
        "auth_version": 1, "amr": ["email_otp"],
    }
    monkeypatch.setattr(auth_dependency, "decode_access_token", lambda _: payload)
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")
    with pytest.raises(HTTPException) as unverified:
        await auth_dependency.get_current_user(credential, db)
    assert unverified.value.status_code == 401

    await db.users.update_one({"_id": user_id}, {"$set": {"is_verified": True}})
    payload["amr"] = ["password"]
    with pytest.raises(HTTPException) as password_only:
        await auth_dependency.get_current_user(credential, db)
    assert password_only.value.status_code == 401

    payload["amr"] = ["email_otp"]
    with pytest.raises(HTTPException) as otp_only:
        await auth_dependency.get_current_user(credential, db)
    assert otp_only.value.status_code == 401

    payload["amr"] = ["password", "email_otp"]
    assert (await auth_dependency.get_current_user(credential, db))["user_id"] == str(user_id)
