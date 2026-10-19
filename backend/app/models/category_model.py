"""models/category_model.py"""
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if "created_at" in doc and isinstance(doc["created_at"], datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    if "updated_at" in doc and isinstance(doc["updated_at"], datetime):
        doc["updated_at"] = doc["updated_at"].isoformat()
    return doc


async def list_categories(db: AsyncIOMotorDatabase) -> list[dict]:
    docs = await db.categories.find({}, {"name": 1}).sort("name", 1).to_list(length=1000)
    return [_serialize(d) for d in docs]


async def seed_default_categories(db: AsyncIOMotorDatabase) -> None:
    now = datetime.now(timezone.utc)
    defaults = [
        {"name": "Electronics", "created_at": now, "updated_at": now},
        {"name": "Accessories", "created_at": now, "updated_at": now},
        {"name": "Home Office", "created_at": now, "updated_at": now},
        {"name": "Kitchen", "created_at": now, "updated_at": now},
        {"name": "Clothing", "created_at": now, "updated_at": now},
        {"name": "Fitness", "created_at": now, "updated_at": now},
    ]
    # Safe under multi-process startup: upsert by unique `name`
    for c in defaults:
        await db.categories.update_one(
            {"name": {"$eq": c["name"]}},
            {"$setOnInsert": c},
            upsert=True,
        )
