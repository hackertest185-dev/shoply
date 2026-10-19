"""
models/review_model.py
MongoDB access helpers for product reviews.
"""
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    for field in ("product_id", "customer_id"):
        if field in doc:
            doc[field] = str(doc[field])
    for field in ("created_at", "updated_at"):
        if field in doc:
            doc[field] = doc[field].isoformat()
    return doc


async def create_review(
    db: AsyncIOMotorDatabase, product_id: str, customer_id: str, rating: int, body: str
) -> dict:
    now = datetime.now(timezone.utc)
    data = {
        "product_id": ObjectId(product_id),
        "customer_id": ObjectId(customer_id),
        "rating": rating,
        "body": body,
        "created_at": now,
        "updated_at": now,
    }
    await db.reviews.insert_one(data)
    await _recompute_rating(db, product_id)
    return _serialize(data.copy())


async def list_reviews(
    db: AsyncIOMotorDatabase, product_id: str, page: int = 1, limit: int = 20
) -> tuple[list[dict], int]:
    skip = (page - 1) * limit
    cursor = (
        db.reviews.find({"product_id": ObjectId(product_id)})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    total = await db.reviews.count_documents({"product_id": ObjectId(product_id)})
    return [_serialize(d) for d in docs], total


async def get_review(
    db: AsyncIOMotorDatabase, product_id: str, customer_id: str
) -> dict | None:
    doc = await db.reviews.find_one(
        {"product_id": ObjectId(product_id), "customer_id": ObjectId(customer_id)}
    )
    return _serialize(doc) if doc else None


async def update_review(
    db: AsyncIOMotorDatabase,
    product_id: str,
    customer_id: str,
    rating: int,
    body: str,
) -> None:
    await db.reviews.update_one(
        {"product_id": ObjectId(product_id), "customer_id": ObjectId(customer_id)},
        {
            "$set": {
                "rating": rating,
                "body": body,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    await _recompute_rating(db, product_id)


async def delete_review(
    db: AsyncIOMotorDatabase, product_id: str, customer_id: str
) -> None:
    await db.reviews.delete_one(
        {"product_id": ObjectId(product_id), "customer_id": ObjectId(customer_id)}
    )
    await _recompute_rating(db, product_id)


async def get_rating(db: AsyncIOMotorDatabase, product_id: str) -> dict:
    pipeline = [
        {"$match": {"product_id": ObjectId(product_id)}},
        {"$group": {"_id": None, "average": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]
    res = await db.reviews.aggregate(pipeline).to_list(length=1)
    if res and res[0]["count"] > 0:
        return {"average": round(float(res[0]["average"]), 2), "count": res[0]["count"]}
    return {"average": 0.0, "count": 0}


async def _recompute_rating(db: AsyncIOMotorDatabase, product_id: str) -> None:
    rating = await get_rating(db, product_id)
    await db.products.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"ratings": rating, "updated_at": datetime.now(timezone.utc)}},
    )
