"""
models/user_model.py
MongoDB access helpers for the users collection.
All queries use $eq for equality — prevents operator injection.
Response projection NEVER includes password_hash or internal fields.
"""
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

SAFE_PROJECTION = {
    "password_hash": 0,
    "failed_login_count": 0,
    "account_locked_until": 0,
    "verification_token": 0,
    "verification_token_expires": 0,
    "auth_version": 0,
    "__v": 0,
}


def _serialize(doc: dict) -> dict:
    """Convert ObjectId → str and datetime → ISO string."""
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    if "created_at" in doc:
        doc["created_at"] = doc["created_at"].isoformat()
    if "updated_at" in doc:
        doc["updated_at"] = doc["updated_at"].isoformat()
    return doc


async def find_by_email(db: AsyncIOMotorDatabase, email: str) -> dict | None:
    """Find user by email. Returns full document including password_hash (for auth only)."""
    return await db.users.find_one({"email": {"$eq": email.lower().strip()}})


async def find_by_id(db: AsyncIOMotorDatabase, user_id: str) -> dict | None:
    """Find user by ID with safe projection (no password_hash)."""
    if not ObjectId.is_valid(user_id):
        return None
    doc = await db.users.find_one(
        {"_id": ObjectId(user_id)},
        SAFE_PROJECTION,
    )
    return _serialize(doc) if doc else None


async def insert_user(db: AsyncIOMotorDatabase, data: dict) -> str:
    """Insert a new user document. Returns inserted_id as string."""
    now = datetime.now(timezone.utc)
    data["created_at"] = now
    data["updated_at"] = now
    data["failed_login_count"] = 0
    data["account_locked_until"] = None
    data.setdefault("auth_version", 1)
    result = await db.users.insert_one(data)
    return str(result.inserted_id)


_SENSITIVE_USER_FIELDS = {
    "role", "password_hash", "auth_version", "is_verified", "status",
    "failed_login_count", "account_locked_until", "verification_token",
    "verification_token_expires",
}


async def update_user(
    db: AsyncIOMotorDatabase,
    user_id: str,
    updates: dict,
    *,
    allow_sensitive: bool = False,
) -> None:
    """Partial update with an explicit guard for identity/security fields."""
    if not ObjectId.is_valid(user_id):
        raise ValueError("INVALID_USER_ID")
    if not allow_sensitive and _SENSITIVE_USER_FIELDS.intersection(updates):
        raise ValueError("SENSITIVE_USER_UPDATE_FORBIDDEN")
    if any(str(key).startswith("$") or "." in str(key) for key in updates):
        raise ValueError("INVALID_USER_UPDATE")
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": updates},
    )


async def increment_failed_logins(db: AsyncIOMotorDatabase, user_id: str) -> int:
    """Increment failed_login_count. Returns new count."""
    result = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$inc": {"failed_login_count": 1}},
        return_document=True,
        projection={"failed_login_count": 1},
    )
    return result["failed_login_count"] if result else 0


async def reset_failed_logins(db: AsyncIOMotorDatabase, user_id: str) -> None:
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"failed_login_count": 0, "account_locked_until": None}},
    )


async def bump_auth_version(db: AsyncIOMotorDatabase, user_id: str) -> int:
    """Invalidate all previously issued access tokens for a user."""
    result = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$inc": {"auth_version": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        return_document=True,
        projection={"auth_version": 1},
    )
    return int((result or {}).get("auth_version", 1))
