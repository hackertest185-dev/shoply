"""
dependencies/verified_dependency.py  ★
Checks verificationStatus from DB — NOT from JWT — on every delivery route.
This prevents stale-token bypass: an agent rejected after login is blocked
immediately on the next request.
"""
from fastapi import Depends, HTTPException, status
from bson import ObjectId

from app.core.database import get_db
from .rbac_dependency import require_delivery


async def require_verified_delivery(
    current_user: dict = Depends(require_delivery),
    db=Depends(get_db),
) -> dict:
    """
    Passes only when:
    1. Role is 'delivery' (enforced by require_delivery above)
    2. verification_status in DB == 'approved'
    Always reads from DB — never trusts JWT payload for this check.
    """
    user = await db.users.find_one(
        {"_id": ObjectId(current_user["user_id"])},
        {"verification_status": 1},
    )

    if not user or user.get("verification_status") != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_VERIFIED",
                "message": (
                    "Your account is pending verification. "
                    "Please complete document submission at /verification."
                ),
            },
        )

    return current_user
