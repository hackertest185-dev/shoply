"""Customer product review API flow."""
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_customer_can_create_and_read_a_product_review():
    db = AsyncMongoMockClient().shoply_review_test
    product_id = ObjectId()
    customer_id = str(ObjectId())
    await db.products.insert_one({
        "_id": product_id,
        "name": "Review test product",
        "status": "active",
    })
    identity = {"user_id": customer_id, "email": "reviewer@example.com", "role": "customer"}

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identity
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/v1/products/{product_id}/reviews"
            created = await client.post(path, json={"rating": 5, "body": "Very useful product."})
            assert created.status_code == 201
            assert created.json()["data"]["body"] == "Very useful product."

            listed = await client.get(path)
            assert listed.status_code == 200
            assert listed.json()["meta"]["total"] == 1
            assert listed.json()["data"][0]["id"] == created.json()["data"]["id"]

            duplicate = await client.post(path, json={"rating": 4, "body": "Another review text."})
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"]["code"] == "REVIEW_EXISTS"
    finally:
        app.dependency_overrides.clear()
