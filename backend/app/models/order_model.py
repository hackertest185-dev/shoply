"""models/order_model.py"""
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    # Storage keys are never sent to browsers.  A future proof-download route
    # must authorize the order first and mint a short-lived signed URL.
    doc.pop("proof_of_delivery_key", None)
    doc.pop("proof_of_delivery_url", None)
    doc.pop("payment_intent_id", None)
    if "customer_id" in doc:
        doc["customer_id"] = str(doc["customer_id"])
    if "delivery_id" in doc and doc["delivery_id"]:
        doc["delivery_id"] = str(doc["delivery_id"])
    for field in ("created_at", "updated_at", "admin_contacted_at", "payment_confirmed_at", "delivered_at", "cancelled_at"):
        value = doc.get(field)
        if isinstance(value, datetime):
            # Motor reads MongoDB dates as naive UTC by default. Include the offset
            # so browsers display delivery dates in the customer's time zone.
            doc[field] = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    history = doc.get("status_history") or []
    for event in history:
        if isinstance(event.get("at"), datetime):
            value = event["at"]
            event["at"] = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
        if isinstance(event.get("by"), ObjectId):
            event["by"] = str(event["by"])
    return doc


async def find_by_id(db: AsyncIOMotorDatabase, order_id: str) -> dict | None:
    if not ObjectId.is_valid(order_id):
        return None
    doc = await db.orders.find_one({"_id": ObjectId(order_id)})
    return _serialize(doc) if doc else None


async def find_for_customer(
    db: AsyncIOMotorDatabase, order_id: str, customer_id: str
) -> dict | None:
    """Look up the order and its owner in one database query."""
    if not ObjectId.is_valid(order_id) or not ObjectId.is_valid(customer_id):
        return None
    doc = await db.orders.find_one({
        "_id": ObjectId(order_id),
        "customer_id": ObjectId(customer_id),
    })
    return _serialize(doc) if doc else None


async def find_by_payment_intent(
    db: AsyncIOMotorDatabase, payment_intent_id: str
) -> dict | None:
    doc = await db.orders.find_one(
        {"payment_intent_id": {"$eq": payment_intent_id}}
    )
    return _serialize(doc) if doc else None


async def find_by_delivery_id(
    db: AsyncIOMotorDatabase, delivery_id: str
) -> list[dict]:
    """Find all orders assigned to a delivery agent."""
    cursor = db.orders.find({
        "delivery_id": ObjectId(delivery_id),
    }).sort("created_at", -1).limit(100)
    docs = await cursor.to_list(100)
    return [_serialize(doc) for doc in docs if doc]


async def find_unassigned_orders(
    db: AsyncIOMotorDatabase, limit: int = 50
) -> list[dict]:
    """Find orders that have not been assigned to a delivery agent."""
    cursor = db.orders.find({
        "delivery_id": None,
        "status": {"$nin": ["cancelled", "pending_contact"]},
    }).sort("created_at", 1).limit(limit)
    docs = await cursor.to_list(limit)
    return [_serialize(doc) for doc in docs if doc]


async def insert_order(db: AsyncIOMotorDatabase, data: dict) -> str:
    now = datetime.now(timezone.utc)
    data["created_at"] = now
    data["updated_at"] = now
    data.setdefault("status_history", [{"status": data.get("status", "pending_contact"), "at": now, "by": data.get("customer_id")}])
    result = await db.orders.insert_one(data)
    return str(result.inserted_id)


async def update_order_status(
    db: AsyncIOMotorDatabase,
    order_id: str,
    status: str,
    delivery_status: str | None = None,
    extra: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    updates: dict = {"status": status, "updated_at": now}
    if delivery_status:
        updates["delivery_status"] = delivery_status
    if extra:
        updates.update(extra)
    await db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": updates, "$push": {"status_history": {"status": status, "at": now}}},
    )


async def decrement_stock_atomic(
    db: AsyncIOMotorDatabase, items: list[dict]
) -> bool:
    """
    Atomically decrement stock for each item using $inc.
    Returns False if any item would go below 0 (race condition guard).
    """
    changed: list[dict] = []
    for item in items:
        variant_id = item.get("variant_id")
        if variant_id is None:
            # Product has no variant / untracked stock — nothing to decrement.
            continue
        result = await db.products.find_one_and_update(
            {
                "_id": ObjectId(item["product_id"]),
                "variants.id": variant_id,
                "variants.stock_qty": {"$gte": item["qty"]},
            },
            {"$inc": {"variants.$.stock_qty": -item["qty"]}},
            return_document=True,
        )
        if result is None:
            # A single order can contain several variants. Undo any earlier
            # increments when a later item loses a race for stock.
            await restore_stock(db, changed)
            return False  # Insufficient stock
        changed.append(item)
    return True


async def restore_stock(db: AsyncIOMotorDatabase, items: list[dict]) -> None:
    """Return reserved stock when an order is cancelled."""
    for item in items:
        variant_id = item.get("variant_id")
        if variant_id is None or not ObjectId.is_valid(item.get("product_id", "")):
            continue
        await db.products.update_one(
            {"_id": ObjectId(item["product_id"]), "variants.id": variant_id},
            {"$inc": {"variants.$.stock_qty": int(item.get("qty", 0))}},
        )
