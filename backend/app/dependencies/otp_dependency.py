"""
dependencies/otp_dependency.py  ★
Validates OTP from Redis before allowing delivery completion steps.
Reads the 'otp' field from the request body, validated against the
bcrypt hash stored in Redis for the given order_id.
"""
from fastapi import Depends, HTTPException, Request, status
from bson import ObjectId

from app.core.database import get_db
from app.core.redis_client import verify_otp
from .verified_dependency import require_verified_delivery


async def validate_otp(
    request: Request,
    current_user: dict = Depends(require_verified_delivery),
    db=Depends(get_db),
) -> dict:
    """
    Dependency for POST /delivery/orders/{order_id}/verify-otp.
    Reads order_id from path, otp from body.
    Enforces:
    - Agent is assigned to THIS order
    - OTP not locked
    - OTP matches Redis hash
    Returns enriched current_user with order document attached.
    """
    order_id = request.path_params.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": "order_id path parameter required."})

    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})

    # Fetch order and verify assignment
    order = await db.orders.find_one({"_id": oid})
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})

    if str(order.get("delivery_id", "")) != current_user["user_id"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})

    if order.get("delivery_status") not in ("assigned", "otp_verified", "out_for_delivery"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": "Order is not in a deliverable state."},
        )

    # Parse OTP from request body
    try:
        body = await request.json()
        submitted_otp = str(body.get("otp", "")).strip()
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "Request body must be JSON with 'otp' field."})

    if not submitted_otp.isdigit() or len(submitted_otp) != 4:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "OTP must be exactly 4 digits."},
        )

    result = await verify_otp(order_id, submitted_otp)

    if result.get("locked"):
        raise HTTPException(
            status_code=423,
            detail={
                "code": "OTP_LOCKED",
                "message": "Too many incorrect attempts. A new OTP has been sent to the customer.",
            },
        )

    if result.get("expired"):
        raise HTTPException(
            status_code=400,
            detail={"code": "OTP_INVALID", "message": "OTP has expired. Please ask the customer for the latest OTP."},
        )

    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "OTP_INVALID",
                "message": "Incorrect OTP. Please try again.",
                "attempts_remaining": result["attempts_remaining"],
            },
        )

    # OTP verified — attach order to context for the route handler
    return {**current_user, "_order": order, "_order_id": order_id}
