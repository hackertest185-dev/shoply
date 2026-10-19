"""
models/wishlist_model.py
MongoDB access helpers for the customer wishlist.
"""
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    if "user_id" in doc:
        doc["user_id"] = str(doc["user_id"])
    if "product_id" in doc:
        doc["product_id"] = str(doc["product_id"])
    if "created_at" in doc:
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


async def add_item(
    db: AsyncIOMotorDatabase, user_id: str, product_id: str
) -> bool:
    """Add a product to the wishlist. Returns True if newly added."""
    now = datetime.now(timezone.utc)
    data = {
        "user_id": ObjectId(user_id),
        "product_id": ObjectId(product_id),
        "created_at": now,
    }
    try:
        await db.wishlists.insert_one(data)
        return True
    except Exception:
        # Duplicate (unique index) — already in wishlist
        return False


async def remove_item(
    db: AsyncIOMotorDatabase, user_id: str, product_id: str
) -> bool:
    result = await db.wishlists.delete_one(
        {"user_id": ObjectId(user_id), "product_id": ObjectId(product_id)}
    )
    return result.deleted_count > 0


async def list_item_ids(
    db: AsyncIOMotorDatabase, user_id: str
) -> list[str]:
    cursor = db.wishlists.find({"user_id": ObjectId(user_id)}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [str(d["product_id"]) for d in docs]


async def is_in_wishlist(
    db: AsyncIOMotorDatabase, user_id: str, product_id: str
) -> bool:
    doc = await db.wishlists.find_one(
        {"user_id": ObjectId(user_id), "product_id": ObjectId(product_id)}
    )
    return doc is not None
