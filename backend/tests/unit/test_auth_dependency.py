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
    })
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")

    identity = await auth_dependency.get_current_user(credential, db)
    assert identity["role"] == "customer"

    await db.users.update_one({"_id": user_id}, {"$set": {"status": "suspended"}})
    with pytest.raises(HTTPException) as error:
        await auth_dependency.get_current_user(credential, db)
    assert error.value.status_code == 401
