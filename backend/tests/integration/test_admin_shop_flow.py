"""Admin catalog and customer WhatsApp ordering contract."""
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_only_admin_can_publish_product_and_customer_can_request_order():
    db = AsyncMongoMockClient().shoply_test
    category_id = ObjectId()
    await db.categories.insert_one({"_id": category_id, "name": "Accessories"})
    customer_id = str(ObjectId())
    admin_id = str(ObjectId())
    identity = {"user_id": customer_id, "email": "buyer@example.com", "role": "customer"}

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identity
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            product = {
                "name": "Test headphones",
                "description": "Headphones for the shop flow test",
                "price": 25.0,
                "category_id": str(category_id),
                "images": ["data:image/png;base64,aGVsbG8="],
                "variants": [{"sku": "TEST-HEADPHONES", "stock_qty": 3}],
            }
            denied = await client.post("/api/v1/products", json=product)
            assert denied.status_code == 403

            identity.update(user_id=admin_id, role="admin")
            created = await client.post("/api/v1/products", json=product)
            assert created.status_code == 201
            assert created.json()["data"]["status"] == "active"
            product_id = created.json()["data"]["id"]

            identity.update(user_id=customer_id, role="customer")
            catalog = await client.get("/api/v1/products")
            assert catalog.status_code == 200
            assert any(item["id"] == product_id for item in catalog.json()["data"])

            added = await client.post("/api/v1/cart/items", json={"product_id": product_id, "qty": 1})
            assert added.status_code == 201
            invalid = await client.post("/api/v1/orders", json={"whatsapp_number": "12345"})
            assert invalid.status_code == 422
            order = await client.post("/api/v1/orders", json={"whatsapp_number": "+201234567890"})
            assert order.status_code == 201
            assert order.json()["data"]["payment_status"] == "unpaid"
            order_id = order.json()["data"]["order_id"]

            identity.update(user_id=admin_id, role="admin")
            pending = await client.get("/api/v1/admin/orders?status=pending_contact")
            assert pending.status_code == 200
            assert any(
                item["id"] == order_id and item["whatsapp_number"] == "+201234567890"
                for item in pending.json()["data"]
            )

            contacted = await client.post(f"/api/v1/admin/orders/{order_id}/whatsapp-contacted")
            assert contacted.status_code == 200
            assert contacted.json()["data"]["contact_status"] == "contacted"

            identity.update(user_id=customer_id, role="customer")
            customer_orders = await client.get("/api/v1/orders?page=1&limit=20")
            assert customer_orders.status_code == 200
            assert any(
                item["id"] == order_id and item["contact_status"] == "contacted"
                for item in customer_orders.json()["data"]
            )
    finally:
        app.dependency_overrides.clear()
