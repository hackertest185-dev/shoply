"""
routers/wishlist_router.py
Customer wishlist — add/remove/list products.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_customer
from app.models import wishlist_model
from app.services import wishlist_service

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


def _ok(data, meta=None):
    r = {"success": True, "data": data, "request_id": str(uuid.uuid4())}
    if meta:
        r["meta"] = meta
    return r


@router.get("")
async def list_wishlist(
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    products = await wishlist_service.list_wishlist_products(db, current_user["user_id"])
    return _ok(products)


@router.post("/{product_id}", status_code=status.HTTP_201_CREATED)
async def toggle_wishlist(
    product_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    result = await wishlist_service.toggle_wishlist(db, current_user["user_id"], product_id)
    return _ok(result)


@router.delete("/{product_id}")
async def remove_from_wishlist(
    product_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    removed = await wishlist_model.remove_item(db, current_user["user_id"], product_id)
    if not removed:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok({"action": "removed"})


@router.get("/{product_id}/status")
async def wishlist_status(
    product_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    in_wishlist = await wishlist_model.is_in_wishlist(db, current_user["user_id"], product_id)
    return _ok({"in_wishlist": in_wishlist})
