"""models/product_model.py"""
import re
import uuid
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug[:100]


async def _unique_slug(db: AsyncIOMotorDatabase, name: str) -> str:
    """Create a URL-safe slug that also works for non-Latin product names."""
    base = _slugify(name) or f"product-{uuid.uuid4().hex[:12]}"
    candidate = base
    for _ in range(8):
        existing = await db.products.find_one({"slug": {"$eq": candidate}}, {"_id": 1})
        if not existing:
            return candidate
        candidate = f"{base[:87].rstrip('-')}-{uuid.uuid4().hex[:12]}"
    return f"product-{uuid.uuid4().hex}"


def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    if "vendor_id" in doc:
        doc["vendor_id"] = str(doc["vendor_id"])
    if "category_id" in doc:
        doc["category_id"] = str(doc["category_id"])
    for field in ("created_at", "updated_at"):
        if field in doc and isinstance(doc[field], datetime):
            doc[field] = doc[field].isoformat()
    return doc


async def insert_product(db: AsyncIOMotorDatabase, data: dict) -> str:
    now = datetime.now(timezone.utc)
    data["created_at"] = now
    data["updated_at"] = now
    data["ratings"] = {"average": 0.0, "count": 0}
    data["slug"] = await _unique_slug(db, data["name"])
    result = await db.products.insert_one(data)
    return str(result.inserted_id)


async def find_by_id(db: AsyncIOMotorDatabase, product_id: str) -> dict | None:
    try:
        oid = ObjectId(product_id)
    except (InvalidId, TypeError):
        return None
    doc = await db.products.find_one({"_id": oid})
    return _serialize(doc) if doc else None


async def list_products(
    db: AsyncIOMotorDatabase,
    filters: dict,
    skip: int,
    limit: int,
    sort_field: str,
    sort_dir: int,
) -> tuple[list[dict], int]:
    cursor = db.products.find(filters).sort(sort_field, sort_dir).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    total = await db.products.count_documents(filters)
    return [_serialize(d) for d in docs], total


async def list_products_for_vendor(
    db: AsyncIOMotorDatabase, vendor_id: str, limit: int = 50
) -> list[dict]:
    doc_limit = min(200, max(1, limit))
    cursor = db.products.find({"vendor_id": ObjectId(vendor_id)}).sort("created_at", -1).limit(doc_limit)
    docs = await cursor.to_list(length=doc_limit)
    return [_serialize(d) for d in docs]


async def list_products_for_admin(db: AsyncIOMotorDatabase, limit: int = 50) -> list[dict]:
    doc_limit = min(200, max(1, limit))
    docs = await db.products.find({}).sort("created_at", -1).limit(doc_limit).to_list(length=doc_limit)
    return [_serialize(d) for d in docs]


async def update_product(
    db: AsyncIOMotorDatabase, product_id: str, updates: dict
) -> None:
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.products.update_one({"_id": ObjectId(product_id)}, {"$set": updates})
