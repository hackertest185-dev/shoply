"""
core/database.py
Async MongoDB connection via Motor.
Single client instance shared across the application lifecycle.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from .config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Called on FastAPI startup. Creates the Motor client and selects the DB."""
    global _client, _db
    _client = AsyncIOMotorClient(
        settings.MONGO_URI,
        maxPoolSize=50,
        minPoolSize=5,
        serverSelectionTimeoutMS=5000,
    )
    _db = _client[settings.MONGO_DB_NAME]

    # Create indexes on first connect
    await _create_indexes()
    # Seed small lookup collections (safe if already populated)
    await _seed_defaults()


async def close_db() -> None:
    """Called on FastAPI shutdown. Closes the Motor client."""
    global _client
    if _client:
        _client.close()
        _client = None


def get_db() -> AsyncIOMotorDatabase:
    """Dependency-injectable accessor for the database."""
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _db


async def _create_indexes() -> None:
    """Create all required MongoDB indexes at startup."""
    db = get_db()

    # Categories
    try:
        await db.categories.create_index("name", unique=True, background=True)
    except DuplicateKeyError:
        # Older DBs may have duplicate seed rows from multi-process startup.
        await _dedupe_categories()
        await db.categories.create_index("name", unique=True, background=True)

    # Users
    await db.users.create_index("email", unique=True, background=True)
    await db.users.create_index("role", background=True)
    await db.users.create_index("verification_status", background=True)
    await db.users.update_many(
        {"auth_version": {"$exists": False}},
        {"$set": {"auth_version": 1}},
    )

    # Products — text index for full-text search
    await db.products.create_index(
        [("name", "text"), ("description", "text"), ("tags", "text")],
        background=True,
    )
    await db.products.create_index("slug", unique=True, background=True)
    await db.products.create_index("vendor_id", background=True)
    await db.products.create_index("category_id", background=True)
    await db.products.create_index("status", background=True)

    # Orders
    await db.orders.create_index("customer_id", background=True)
    await db.orders.create_index("delivery_id", background=True)
    await db.orders.create_index("status", background=True)
    await db.orders.create_index(
        [("status", 1), ("payment_status", 1), ("delivered_at", -1)],
        background=True,
    )
    await db.orders.create_index("payment_intent_id", unique=True, sparse=True, background=True)

    # Carts
    await db.carts.create_index("user_id", unique=True, background=True)

    # Refresh tokens
    await db.refresh_tokens.create_index("user_id", background=True)
    await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0, background=True)

    # Wishlist
    await db.wishlists.create_index(
        [("user_id", 1), ("product_id", 1)], unique=True, background=True
    )

    # Delivery documents
    await db.delivery_documents.create_index("user_id", background=True)
    await db.delivery_documents.create_index("status", background=True)

    # Audit logs — append-only, never update/delete
    await db.audit_logs.create_index("actor_id", background=True)
    await db.audit_logs.create_index("action", background=True)
    await db.audit_logs.create_index("created_at", background=True)

    # Reviews
    await db.reviews.create_index(
        [("product_id", 1), ("customer_id", 1)],
        unique=True,
        background=True,
    )


async def _seed_defaults() -> None:
    db = get_db()
    from app.models.category_model import seed_default_categories

    await seed_default_categories(db)


async def _dedupe_categories() -> None:
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$name", "ids": {"$push": "$_id"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    groups = await db.categories.aggregate(pipeline).to_list(length=500)
    for g in groups:
        ids = g.get("ids") or []
        if len(ids) <= 1:
            continue
        # Keep the first, remove the rest
        await db.categories.delete_many({"_id": {"$in": ids[1:]}})
