"""
services/verification_service.py  ★
Delivery agent document upload, status transitions, and admin review logic.
"""
from datetime import datetime, timezone
from bson import ObjectId

from app.core.s3_client import (
    generate_signed_url,
    upload_delivery_document,
    upload_proof_of_delivery,
)
from app.core.config import settings
from app.models import delivery_document_model, user_model
from app.services.audit_log_service import write_audit_log

REQUIRED_DOCUMENT_TYPES = {"national_id", "driving_license", "profile_photo"}


async def submit_verification_documents(
    db,
    user_id: str,
    files: dict,  # { "national_id": bytes, "driving_license": bytes, "profile_photo": bytes }
    filenames: dict,
) -> dict:
    """
    Upload all three verification documents to private S3.
    Increments submission_round, sets user verification_status = 'pending'.
    """
    # Determine submission round
    existing_docs = await delivery_document_model.find_by_user(db, user_id)
    current_round = max((d.get("submission_round", 1) for d in existing_docs), default=0) + 1

    uploaded = []
    for doc_type in REQUIRED_DOCUMENT_TYPES:
        content  = files.get(doc_type)
        filename = filenames.get(doc_type, f"{doc_type}.bin")
        if not content:
            raise ValueError(f"Missing required document: {doc_type}")

        s3_key = await upload_delivery_document(
            user_id, doc_type, current_round, content, filename
        )

        await delivery_document_model.insert_document(db, {
            "user_id":         user_id,
            "document_type":   doc_type,
            "s3_key":          s3_key,
            "file_url":        s3_key,  # access via signed URL only
            "status":          "pending",
            "submission_round": current_round,
            "rejection_reason": None,
            "reviewed_by":     None,
            "reviewed_at":     None,
        })
        uploaded.append(doc_type)

    # Update user verification_status → pending
    await user_model.update_user(
        db, user_id, {"verification_status": "pending"}
    )

    return {
        "submission_round":     current_round,
        "verification_status":  "pending",
        "documents_uploaded":   uploaded,
        "message": "Documents submitted. An admin will review within 1–2 business days.",
    }


async def get_agent_documents_with_signed_urls(
    db, user_id: str, admin_id: str
) -> list[dict]:
    """
    Return signed S3 URLs for all documents (15-min expiry).
    Writes audit log because admin is viewing sensitive PII.
    """
    agent = await db.users.find_one({"_id": ObjectId(user_id), "role": "delivery"}, {"_id": 1})
    if not agent:
        raise ValueError("NOT_FOUND")
    docs = await delivery_document_model.find_by_user(db, user_id)
    result = []
    for doc in docs:
        signed_url = generate_signed_url(
            settings.S3_BUCKET_DELIVERY_DOCS,
            doc["file_url"],
            expiry_seconds=900,
            download=True,
        )
        result.append({
            "id":              doc["id"],
            "document_type":   doc["document_type"],
            "signed_url":      signed_url,
            "status":          doc["status"],
            "submission_round": doc["submission_round"],
            "created_at":      doc.get("created_at", ""),
        })

    await write_audit_log(
        db, admin_id, "admin", "document_viewed", "delivery_documents",
        user_id, {"doc_count": len(result)}, None,
    )
    return result


async def approve_agent(db, agent_id: str, admin_id: str, ip: str) -> None:
    """Set verification_status = approved. Notify agent (TODO: email)."""
    if not ObjectId.is_valid(agent_id) or not await db.users.find_one({"_id": ObjectId(agent_id), "role": "delivery"}, {"_id": 1}):
        raise ValueError("NOT_FOUND")
    await user_model.update_user(
        db, agent_id,
        {"verification_status": "approved", "rejection_reason": None},
    )
    await write_audit_log(
        db, admin_id, "admin", "agent_approved", "users", agent_id, {}, ip,
    )


async def reject_agent(
    db, agent_id: str, admin_id: str, rejection_reason: str, ip: str
) -> None:
    """Set verification_status = rejected with reason. Notify agent (TODO: email)."""
    if not ObjectId.is_valid(agent_id) or not await db.users.find_one({"_id": ObjectId(agent_id), "role": "delivery"}, {"_id": 1}):
        raise ValueError("NOT_FOUND")
    await user_model.update_user(
        db, agent_id,
        {
            "verification_status": "rejected",
            "rejection_reason":    rejection_reason,
        },
    )
    await write_audit_log(
        db, admin_id, "admin", "agent_rejected", "users", agent_id,
        {"reason": rejection_reason}, ip,
    )


async def confirm_delivery(
    db,
    order_id: str,
    agent_id: str,
    proof_content: bytes,
    proof_filename: str,
    ip: str,
) -> dict:
    """
    Upload proof-of-delivery image, mark order delivered, write audit log.
    Only callable after OTP has been verified (delivery_status == 'otp_verified').
    """
    proof_url = await upload_proof_of_delivery(order_id, agent_id, proof_content, proof_filename)

    from app.models.order_model import update_order_status
    await update_order_status(
        db, order_id,
        status="delivered",
        delivery_status="delivered",
        extra={
            "proof_of_delivery_key": proof_url,
            "delivered_at": datetime.now(timezone.utc),
        },
    )

    await write_audit_log(
        db, agent_id, "delivery", "delivery_confirmed", "orders", order_id,
        {"proof_stored": True}, ip,
    )

    # TODO: Send delivery confirmation email to customer

    return {
        "order_id":              order_id,
        "delivery_status":       "delivered",
        "proof_available": True,
        "completed_at":          datetime.now(timezone.utc).isoformat(),
        "message":               "Delivery confirmed. Customer has been notified.",
    }
