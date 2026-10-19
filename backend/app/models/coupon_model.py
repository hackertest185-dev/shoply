"""MongoDB helpers for discount coupons.

Coupons are deliberately kept separate from orders so an admin can deactivate a
code without changing historical order totals.
"""
from datetime import datetime, timezone
from bson import ObjectId


def _serialize(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    for field in ("expires_at", "created_at", "updated_at"):
        if isinstance(doc.get(field), datetime):
            value = doc[field]
            doc[field] = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return doc


async def find_by_code(db, code: str) -> dict | None:
    return await db.coupons.find_one({"code": {"$eq": code.strip().upper()}})


async def list_coupons(db, limit: int = 100) -> list[dict]:
    docs = await db.coupons.find({}).sort("created_at", -1).limit(limit).to_list(limit)
    return [_serialize(doc) for doc in docs]


async def insert_coupon(db, data: dict) -> str:
    now = datetime.now(timezone.utc)
    data = {**data, "code": data["code"].strip().upper(), "created_at": now, "updated_at": now, "used_count": 0}
    result = await db.coupons.insert_one(data)
    return str(result.inserted_id)


async def update_coupon(db, coupon_id: str, updates: dict) -> bool:
    if not ObjectId.is_valid(coupon_id):
        return False
    updates = {**updates, "updated_at": datetime.now(timezone.utc)}
    result = await db.coupons.update_one({"_id": ObjectId(coupon_id)}, {"$set": updates})
    return result.matched_count == 1


async def delete_coupon(db, coupon_id: str) -> bool:
    if not ObjectId.is_valid(coupon_id):
        return False
    result = await db.coupons.update_one(
        {"_id": ObjectId(coupon_id)},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.matched_count == 1


async def increment_usage(db, coupon_id: str) -> bool:
    """Increment usage only while the coupon is still within its use limit."""
    if not ObjectId.is_valid(coupon_id):
        return False
    now = datetime.now(timezone.utc)
    query = {
        "_id": ObjectId(coupon_id),
        "active": True,
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
        "$expr": {"$or": [{"$eq": [{"$ifNull": ["$max_uses", 0]}, 0]}, {"$lt": ["$used_count", "$max_uses"]}]},
    }
    result = await db.coupons.update_one(query, {"$inc": {"used_count": 1}})
    return result.modified_count == 1
