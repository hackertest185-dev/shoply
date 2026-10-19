"""
models/audit_log_model.py  ★
Append-only audit log. No update or delete operations exist.
"""
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase


async def append_log(
    db: AsyncIOMotorDatabase,
    actor_id: str,
    actor_role: str,
    action: str,
    target_entity: str,
    target_id: str | None,
    metadata: dict | None,
    ip: str | None,
) -> None:
    """Write one immutable audit record. Never called for update/delete."""
    await db.audit_logs.insert_one({
        "actor_id":     actor_id,
        "actor_role":   actor_role,
        "action":       action,
        "target_entity": target_entity,
        "target_id":    target_id,
        "metadata":     metadata or {},
        "ip":           ip,
        "created_at":   datetime.now(timezone.utc),
    })
