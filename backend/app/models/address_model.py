"""
models/address_model.py
MongoDB access helpers for customer addresses.
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
    for field in ("created_at", "updated_at"):
        if field in doc:
            doc[field] = doc[field].isoformat()
    return doc


async def insert_address(db: AsyncIOMotorDatabase, user_id: str, data: dict) -> str:
    now = datetime.now(timezone.utc)
    data["user_id"] = ObjectId(user_id)
    data["created_at"] = now
    data["updated_at"] = now
    if data.get("is_default"):
        await db.addresses.update_many(
            {"user_id": ObjectId(user_id), "is_default": True},
            {"$set": {"is_default": False}},
        )
    result = await db.addresses.insert_one(data)
    return str(result.inserted_id)


async def list_addresses(db: AsyncIOMotorDatabase, user_id: str) -> list[dict]:
    cursor = db.addresses.find({"user_id": ObjectId(user_id)}).sort("is_default", -1).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return [_serialize(d) for d in docs]


async def get_address(db: AsyncIOMotorDatabase, address_id: str, user_id: str) -> dict | None:
    if not ObjectId.is_valid(address_id):
        return None
    doc = await db.addresses.find_one({"_id": ObjectId(address_id), "user_id": ObjectId(user_id)})
    return _serialize(doc) if doc else None


async def update_address(
    db: AsyncIOMotorDatabase, address_id: str, user_id: str, updates: dict
) -> bool:
    if not ObjectId.is_valid(address_id):
        return False
    target = {"_id": ObjectId(address_id), "user_id": ObjectId(user_id)}
    if not await db.addresses.find_one(target, {"_id": 1}):
        return False
    updates["updated_at"] = datetime.now(timezone.utc)
    if updates.get("is_default"):
        await db.addresses.update_many(
            {"user_id": ObjectId(user_id), "is_default": True},
            {"$set": {"is_default": False}},
        )
    result = await db.addresses.update_one(target, {"$set": updates})
    return result.matched_count > 0


async def delete_address(db: AsyncIOMotorDatabase, address_id: str, user_id: str) -> bool:
    if not ObjectId.is_valid(address_id):
        return False
    result = await db.addresses.delete_one({"_id": ObjectId(address_id), "user_id": ObjectId(user_id)})
    return result.deleted_count > 0
