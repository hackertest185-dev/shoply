"""models/delivery_document_model.py  ★"""
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def insert_document(db: AsyncIOMotorDatabase, data: dict) -> str:
    now = datetime.now(timezone.utc)
    data["created_at"] = now
    data["updated_at"] = now
    result = await db.delivery_documents.insert_one(data)
    return str(result.inserted_id)


async def find_by_user(
    db: AsyncIOMotorDatabase, user_id: str, submission_round: int | None = None
) -> list[dict]:
    query: dict = {"user_id": {"$eq": user_id}}
    if submission_round is not None:
        query["submission_round"] = {"$eq": submission_round}
    cursor = db.delivery_documents.find(query)
    docs = await cursor.to_list(length=20)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs


async def update_document_status(
    db: AsyncIOMotorDatabase,
    doc_id: str,
    status: str,
    reviewed_by: str,
    rejection_reason: str | None = None,
) -> None:
    updates: dict = {
        "status":      status,
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc),
        "updated_at":  datetime.now(timezone.utc),
    }
    if rejection_reason:
        updates["rejection_reason"] = rejection_reason
    await db.delivery_documents.update_one(
        {"_id": ObjectId(doc_id)}, {"$set": updates}
    )
