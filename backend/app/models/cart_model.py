"""models/cart_model.py"""
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_cart(db: AsyncIOMotorDatabase, user_id: str) -> dict | None:
    return await db.carts.find_one({"user_id": {"$eq": user_id}})


async def upsert_cart(db: AsyncIOMotorDatabase, user_id: str, items: list[dict]) -> None:
    await db.carts.update_one(
        {"user_id": {"$eq": user_id}},
        {"$set": {"items": items, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def clear_cart(db: AsyncIOMotorDatabase, user_id: str) -> None:
    await db.carts.update_one(
        {"user_id": {"$eq": user_id}},
        {"$set": {"items": [], "updated_at": datetime.now(timezone.utc)}},
    )
