"""
models/audit_log_model.py  ★
Append-only audit log. No update or delete operations exist.
"""
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.request_context import request_id_context

_SENSITIVE_KEYS = {
    "password", "password_hash", "otp", "token", "access_token", "refresh_token",
    "authorization", "cookie", "signed_url", "proof_url", "whatsapp_number",
}


def _redact(value):
    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


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
        "metadata":     _redact(metadata or {}),
        "ip":           ip,
        "request_id":   request_id_context.get(),
        "created_at":   datetime.now(timezone.utc),
    })
