"""Delivered purchases, receipt access, sales, and cross-account isolation."""
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_only_buyer_gets_receipt_after_admin_confirms_paid_delivery():
    db = AsyncMongoMockClient().shoply_test
    buyer_id, stranger_id, admin_id = (str(ObjectId()) for _ in range(3))
    await db.users.insert_many([
        {"_id": ObjectId(buyer_id), "name": "Buyer One", "role": "customer"},
        {"_id": ObjectId(stranger_id), "name": "Buyer Two", "role": "customer"},
        {"_id": ObjectId(admin_id), "name": "Store Admin", "role": "admin"},
    ])
    order_id = str(ObjectId())
    await db.orders.insert_one({
        "_id": ObjectId(order_id),
        "customer_id": ObjectId(buyer_id),
        "items": [{"product_id": str(ObjectId()), "name": "Linen cushion", "qty": 2, "unit_price": 125.0}],
        "items_count": 2,
        "whatsapp_number": "+201234567890",
        "status": "pending_contact",
        "delivery_status": "awaiting_confirmation",
        "payment_status": "unpaid",
        "contact_status": "not_contacted",
        "subtotal": 250.0,
        "tax": 0.0,
        "shipping_cost": 0.0,
        "total": 250.0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    identity = {"user_id": buyer_id, "email": "buyer@example.com", "role": "customer"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identity
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            own = await client.get("/api/v1/orders")
            assert own.status_code == 200
            assert [item["id"] for item in own.json()["data"]] == [order_id]
            before = await client.get(f"/api/v1/orders/{order_id}/receipt")
            assert before.status_code == 409

            identity.update(user_id=stranger_id, email="stranger@example.com")
            other_list = await client.get("/api/v1/orders")
            assert other_list.json()["data"] == []
            assert (await client.get(f"/api/v1/orders/{order_id}")).status_code == 404
            assert (await client.get(f"/api/v1/orders/{order_id}/receipt")).status_code == 404
            assert (await client.post(f"/api/v1/admin/orders/{order_id}/deliver", json={"payment_received": True})).status_code == 403
            assert (await client.get("/api/v1/admin/sales/summary")).status_code == 403

            identity.update(user_id=admin_id, role="admin")
            assert (await client.post(f"/api/v1/admin/orders/{order_id}/deliver", json={"payment_received": True})).status_code == 409
            contacted = await client.post(f"/api/v1/admin/orders/{order_id}/whatsapp-contacted")
            assert contacted.status_code == 200
            assert (await client.post(f"/api/v1/admin/orders/{order_id}/whatsapp-contacted")).status_code == 409
            assert (await client.post(f"/api/v1/admin/orders/{order_id}/deliver", json={"payment_received": False})).status_code == 422
            delivered = await client.post(f"/api/v1/admin/orders/{order_id}/deliver", json={"payment_received": True})
            assert delivered.status_code == 200
            assert delivered.json()["data"]["payment_status"] == "paid"
            assert (await client.post(f"/api/v1/admin/orders/{order_id}/deliver", json={"payment_received": True})).status_code == 409

            sales = await client.get("/api/v1/admin/sales/summary?days=7")
            assert sales.status_code == 200
            assert sales.json()["data"]["delivered_orders"] == 1
            assert sales.json()["data"]["items_sold"] == 2
            assert sales.json()["data"]["total_revenue"] == 250.0
            assert sales.json()["data"]["period_revenue"] == 250.0
            completed = await client.get("/api/v1/admin/orders?status=delivered")
            assert [item["id"] for item in completed.json()["data"]] == [order_id]
            assert completed.json()["data"][0]["delivered_at"].endswith("+00:00")

            identity.update(user_id=buyer_id, email="buyer@example.com", role="customer")
            receipt = await client.get(f"/api/v1/orders/{order_id}/receipt")
            assert receipt.status_code == 200
            assert receipt.headers["content-type"] == "application/pdf"
            assert receipt.headers["cache-control"] == "private, no-store"
            assert receipt.content.startswith(b"%PDF-")
            assert len(receipt.content) > 1500
            detail = await client.get(f"/api/v1/orders/{order_id}")
            assert detail.json()["data"]["items"][0]["name"] == "Linen cushion"
            own_orders = await client.get("/api/v1/orders")
            assert own_orders.json()["data"][0]["delivered_at"].endswith("+00:00")

            identity.update(user_id=stranger_id, email="stranger@example.com")
            assert (await client.get(f"/api/v1/orders/{order_id}/receipt")).status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_address_update_does_not_change_another_customers_address_or_defaults():
    db = AsyncMongoMockClient().shoply_test
    owner_id, stranger_id = str(ObjectId()), str(ObjectId())
    target_id, own_default_id = ObjectId(), ObjectId()
    await db.addresses.insert_many([
        {"_id": target_id, "user_id": ObjectId(owner_id), "label": "Home", "is_default": True},
        {"_id": own_default_id, "user_id": ObjectId(stranger_id), "label": "My home", "is_default": True},
    ])
    identity = {"user_id": stranger_id, "role": "customer"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identity
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            changed = await client.patch(
                f"/api/v1/addresses/{target_id}", json={"label": "Stolen", "is_default": True}
            )
            assert changed.status_code == 404
            assert (await db.addresses.find_one({"_id": target_id}))["label"] == "Home"
            assert (await db.addresses.find_one({"_id": own_default_id}))["is_default"] is True
    finally:
        app.dependency_overrides.clear()
