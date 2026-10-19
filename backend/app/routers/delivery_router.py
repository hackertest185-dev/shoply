"""
routers/delivery_router.py  ★
Delivery agent verification + fulfillment routes.
Dependency chain: auth → rbac(delivery) → verified (for fulfillment) → otp (for verify-otp).
"""
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.database import get_db
from app.core.config import settings
from app.dependencies.rbac_dependency import require_delivery
from app.dependencies.verified_dependency import require_verified_delivery
from app.dependencies.otp_dependency import validate_otp
from app.services import verification_service
from app.models import order_model

router = APIRouter(prefix="/delivery", tags=["Delivery"])
MAX_DOC_SIZE  = settings.DELIVERY_DOCUMENT_MAX_BYTES
MAX_PROOF_SIZE = settings.DELIVERY_PROOF_MAX_BYTES


def _ok(data) -> dict:
    return {"success": True, "data": data, "request_id": str(uuid.uuid4())}


@router.get("/verification/status")
async def get_verification_status(
    current_user: dict = Depends(require_delivery),
    db=Depends(get_db),
):
    """Get own verificationStatus and rejectionReason. Any delivery agent (any status)."""
    from app.models import user_model
    user = await user_model.find_by_id(db, current_user["user_id"])
    return _ok({
        "verification_status": user.get("verification_status"),
        "rejection_reason":    user.get("rejection_reason"),
    })


@router.post("/verification/submit")
async def submit_verification(
    request: Request,
    national_id:     UploadFile = File(..., description="National ID (PDF/JPEG/PNG, max 10MB)"),
    driving_license: UploadFile = File(..., description="Driving License (PDF/JPEG/PNG, max 10MB)"),
    profile_photo:   UploadFile = File(..., description="Profile Photo (JPEG/PNG, max 5MB)"),
    current_user: dict = Depends(require_delivery),
    db=Depends(get_db),
):
    """Upload verification documents. Accessible to pending and rejected delivery agents."""
    files: dict[str, bytes] = {}
    filenames: dict[str, str] = {}
    profile_max = 5 * 1024 * 1024

    for name, upload, max_size in [
        ("national_id",     national_id,     MAX_DOC_SIZE),
        ("driving_license", driving_license, MAX_DOC_SIZE),
        ("profile_photo",   profile_photo,   profile_max),
    ]:
        content = await upload.read(max_size + 1)
        if len(content) > max_size:
            raise HTTPException(
                status_code=400,
                detail={"code": "FILE_TOO_LARGE", "message": f"{name} exceeds {max_size // (1024*1024)}MB limit."},
            )
        files[name]     = content
        filenames[name] = upload.filename or name

    try:
        result = await verification_service.submit_verification_documents(
            db, current_user["user_id"], files, filenames
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "UPLOAD_ERROR", "message": str(exc)})

    return _ok(result)


@router.get("/orders")
async def get_delivery_orders(
    current_user: dict = Depends(require_verified_delivery),
    db=Depends(get_db),
):
    """Get orders assigned to this agent. Only approved agents."""
    from bson import ObjectId
    cursor = db.orders.find({
        "delivery_id": ObjectId(current_user["user_id"]),
        "status":      {"$in": ["confirmed", "out_for_delivery"]},
        "delivery_status": {"$in": ["assigned", "otp_verified"]},
    }).sort("created_at", -1).limit(50)
    docs = await cursor.to_list(50)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
        doc["customer_id"] = str(doc.get("customer_id", ""))
    return _ok(docs)


@router.get("/orders/{order_id}")
async def get_delivery_order(
    order_id: str,
    current_user: dict = Depends(require_verified_delivery),
    db=Depends(get_db),
):
    """Get single order detail — agent must be assigned to it."""
    try:
        order = await order_model.find_by_id(db, order_id)
    except Exception:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if not order or str(order.get("delivery_id", "")) != current_user["user_id"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok(order)


@router.post("/orders/{order_id}/start-delivery")
async def start_delivery(
    order_id: str,
    current_user: dict = Depends(require_verified_delivery),
    db=Depends(get_db),
):
    """Mark order as 'out_for_delivery'. Agent must be assigned and order must be in 'assigned' status."""
    order = await order_model.find_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if str(order.get("delivery_id", "")) != current_user["user_id"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if order.get("delivery_status") != "assigned":
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": "Order is not in assigned state."},
        )

    await order_model.update_order_status(
        db, order_id, status="out_for_delivery", delivery_status="assigned"
    )
    return _ok({
        "order_id":        order_id,
        "status":          "out_for_delivery",
        "delivery_status": "assigned",
        "next_step":       "Ask the customer for their OTP to verify delivery.",
    })


@router.post("/orders/{order_id}/verify-otp")
async def verify_otp_endpoint(
    order_id: str,
    request: Request,
    # otp_dependency validates OTP against Redis and injects enriched user context
    context: dict = Depends(validate_otp),
    db=Depends(get_db),
):
    """
    Validate OTP. otp_dependency has already verified it by this point.
    Advance deliveryStatus to otp_verified.
    """
    await order_model.update_order_status(
        db, order_id, status="out_for_delivery", delivery_status="otp_verified"
    )
    return _ok({
        "order_id":        order_id,
        "delivery_status": "otp_verified",
        "next_step":       "Upload proof of delivery photo to complete the order.",
    })


@router.post("/orders/{order_id}/proof")
async def upload_proof(
    order_id: str,
    request: Request,
    proof_photo: UploadFile = File(..., description="Delivery photo (JPEG/PNG, max 15MB)"),
    current_user: dict = Depends(require_verified_delivery),
    db=Depends(get_db),
):
    """Upload proof-of-delivery. Order must be in otp_verified state."""
    order = await order_model.find_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if str(order.get("delivery_id", "")) != current_user["user_id"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if order.get("delivery_status") != "otp_verified":
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "OTP must be verified before uploading proof."})

    content = await proof_photo.read(MAX_PROOF_SIZE + 1)
    if len(content) > MAX_PROOF_SIZE:
        raise HTTPException(status_code=400, detail={"code": "FILE_TOO_LARGE"})

    ip = request.client.host if request.client else "unknown"
    try:
        result = await verification_service.confirm_delivery(
            db, order_id, current_user["user_id"],
            content, proof_photo.filename or "proof.jpg", ip,
        )
    except ValueError:
        raise HTTPException(status_code=415, detail={"code": "UNSUPPORTED_FILE", "message": "Only valid JPEG and PNG images are allowed."})
    return _ok(result)
