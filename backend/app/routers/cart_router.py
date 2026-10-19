"""routers/cart_router.py"""
import uuid
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_customer
from app.schemas.cart_schema import CartItemAdd, CartItemUpdate
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["Cart"])


def _ok(data) -> dict:
    return {"success": True, "data": data, "request_id": str(uuid.uuid4())}


@router.get("")
async def get_cart(
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    data = await cart_service.get_cart_with_prices(db, current_user["user_id"])
    return _ok(data)


@router.post("/items", status_code=201)
async def add_item(
    body: CartItemAdd,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    try:
        data = await cart_service.add_item(
            db, current_user["user_id"],
            body.product_id, body.variant_id, body.qty,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "INSUFFICIENT_STOCK":
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_STOCK", "message": "Not enough stock."})
        if code == "VARIANT_NOT_FOUND":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Variant not found."})
        if code == "PRODUCT_NOT_FOUND":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Product not found."})
        raise HTTPException(status_code=400, detail={"code": "BAD_REQUEST", "message": str(exc)})
    return _ok(data)


@router.patch("/items/{product_id}")
async def update_item(
    product_id: str,
    body: CartItemUpdate,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    data = await cart_service.update_item(
        db, current_user["user_id"], product_id, body.variant_id, body.qty
    )
    return _ok(data)


@router.delete("/items/{product_id}")
async def remove_item(
    product_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    data = await cart_service.remove_item(db, current_user["user_id"], product_id)
    return _ok(data)


@router.delete("")
async def clear_cart(
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    await cart_service.clear_cart(db, current_user["user_id"])
    return _ok({"message": "Cart cleared."})
