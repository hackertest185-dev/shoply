from datetime import datetime, timezone
from bson import ObjectId


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for key in ("order_id", "customer_id", "sender_id"):
        if doc.get(key) is not None:
            doc[key] = str(doc[key])
    if isinstance(doc.get("created_at"), datetime):
        value = doc["created_at"]
        doc["created_at"] = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return doc


async def list_messages(db, order_id: str, limit: int = 100) -> list[dict]:
    if not ObjectId.is_valid(order_id):
        return []
    docs = await db.order_messages.find({"order_id": ObjectId(order_id)}).sort("created_at", 1).limit(limit).to_list(limit)
    return [_serialize(doc) for doc in docs]


async def insert_message(db, order_id: str, customer_id: str, sender_id: str, sender_role: str, text: str) -> dict:
    now = datetime.now(timezone.utc)
    result = await db.order_messages.insert_one({
        "order_id": ObjectId(order_id),
        "customer_id": ObjectId(customer_id),
        "sender_id": ObjectId(sender_id),
        "sender_role": sender_role,
        "text": text.strip(),
        "created_at": now,
    })
    return _serialize(await db.order_messages.find_one({"_id": result.inserted_id}))
