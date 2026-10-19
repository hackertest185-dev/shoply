import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_admin, require_customer
from app.models import coupon_model
from app.schemas.coupon_schema import CouponCreate, CouponUpdate, CouponValidateRequest

router = APIRouter(prefix="/coupons", tags=["Coupons"])


def _ok(data):
    return {"success": True, "data": data, "request_id": str(uuid.uuid4())}


def _discount(coupon: dict, subtotal: float) -> float:
    if coupon.get("discount_type") == "fixed":
        return min(float(coupon.get("value", 0)), subtotal)
    return min(subtotal, round(subtotal * float(coupon.get("value", 0)) / 100, 2))


async def validate_coupon(db, code: str, subtotal: float) -> dict:
    coupon = await coupon_model.find_by_code(db, code)
    now = datetime.now(timezone.utc)
    if not coupon or not coupon.get("active", False):
        raise ValueError("COUPON_INVALID")
    expires_at = coupon.get("expires_at")
    if expires_at and expires_at.replace(tzinfo=timezone.utc) <= now:
        raise ValueError("COUPON_EXPIRED")
    if coupon.get("max_uses", 0) and coupon.get("used_count", 0) >= coupon["max_uses"]:
        raise ValueError("COUPON_EXHAUSTED")
    if subtotal < float(coupon.get("min_order_total", 0)):
        raise ValueError("COUPON_MINIMUM")
    discount = _discount(coupon, subtotal)
    return {"code": coupon["code"], "discount": discount, "total": round(subtotal - discount, 2), "discount_type": coupon.get("discount_type"), "value": coupon.get("value")}


@router.post("/validate")
async def validate(body: CouponValidateRequest, current_user=Depends(require_customer), db=Depends(get_db)):
    try:
        return _ok(await validate_coupon(db, body.code, body.subtotal))
    except ValueError as exc:
        messages = {
            "COUPON_INVALID": "This coupon is not valid.",
            "COUPON_EXPIRED": "This coupon has expired.",
            "COUPON_EXHAUSTED": "This coupon has reached its usage limit.",
            "COUPON_MINIMUM": "Your order does not reach the coupon minimum.",
        }
        raise HTTPException(status_code=400, detail={"code": str(exc), "message": messages.get(str(exc), "Coupon cannot be used.")})


@router.get("", include_in_schema=False)
async def list_admin(current_user=Depends(require_admin), db=Depends(get_db)):
    return _ok(await coupon_model.list_coupons(db))


@router.post("", status_code=201, include_in_schema=False)
async def create(body: CouponCreate, current_user=Depends(require_admin), db=Depends(get_db)):
    if body.discount_type == "percent" and body.value > 100:
        raise HTTPException(status_code=422, detail={"code": "INVALID_VALUE", "message": "Percent discount cannot exceed 100."})
    try:
        coupon_id = await coupon_model.insert_coupon(db, body.model_dump())
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail={"code": "COUPON_EXISTS", "message": "Coupon code already exists."})
    return _ok({"id": coupon_id})


@router.patch("/{coupon_id}", include_in_schema=False)
async def update(coupon_id: str, body: CouponUpdate, current_user=Depends(require_admin), db=Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    if updates.get("discount_type") == "percent" and updates.get("value", 0) > 100:
        raise HTTPException(status_code=422, detail={"code": "INVALID_VALUE", "message": "Percent discount cannot exceed 100."})
    if not await coupon_model.update_coupon(db, coupon_id, updates):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Coupon not found."})
    return _ok({"message": "Coupon updated."})


@router.delete("/{coupon_id}", include_in_schema=False)
async def remove(coupon_id: str, current_user=Depends(require_admin), db=Depends(get_db)):
    if not await coupon_model.delete_coupon(db, coupon_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Coupon not found."})
    return _ok({"message": "Coupon disabled."})
