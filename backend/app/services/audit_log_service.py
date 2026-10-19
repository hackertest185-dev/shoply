"""
services/audit_log_service.py  ★
Thin wrapper around audit_log_model.append_log.
Called from every service that performs a state change.
"""
from app.models.audit_log_model import append_log


async def write_audit_log(
    db,
    actor_id: str,
    actor_role: str,
    action: str,
    target_entity: str,
    target_id: str | None = None,
    metadata: dict | None = None,
    ip: str | None = None,
) -> None:
    """Fire-and-forget audit write. Never raises — logs on failure instead."""
    try:
        await append_log(
            db=db,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_entity=target_entity,
            target_id=target_id,
            metadata=metadata,
            ip=ip,
        )
    except Exception as exc:
        # Audit failure must never break the main request
        import logging
        logging.getLogger("audit").error("Audit log write failed: %s", exc)
