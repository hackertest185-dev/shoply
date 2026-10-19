"""routers/orders_router.py"""
import uuid
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from bson import ObjectId

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_customer, require_roles
from app.schemas.order_schema import OrderRequest
from app.services import cart_service, orders_service, payment_service, receipt_service
from app.models import order_model

router = APIRouter(tags=["Orders & Checkout"])


def _ok(data, meta=None, code=200) -> dict:
    r = {"success": True, "data": data, "request_id": str(uuid.uuid4())}
    if meta:
        r["meta"] = meta
    return r


@router.post("/orders", status_code=201)
async def request_order(
    body: OrderRequest,
    request: Request,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    """Save a customer's WhatsApp order request for admin follow-up."""
    cart = await cart_service.get_cart_with_prices(db, current_user["user_id"])
    if not cart["items"]:
        raise HTTPException(status_code=400, detail={"code": "CART_EMPTY", "message": "Cart is empty."})
    if cart["warnings"] or any(not item["in_stock"] for item in cart["items"]):
        raise HTTPException(status_code=409, detail={"code": "CART_UNAVAILABLE", "message": "Update your cart before ordering."})

    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key and not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", idempotency_key):
        raise HTTPException(status_code=422, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
    try:
        result = await orders_service.create_contact_request(
            db, current_user["user_id"], body.whatsapp_number, cart,
            request.client.host if request.client else "unknown",
            body.coupon_code,
            idempotency_key,
        )
    except ValueError as exc:
        code = str(exc)
        messages = {
            "INSUFFICIENT_STOCK": "One or more items went out of stock. Refresh your cart.",
            "COUPON_INVALID": "This coupon is not valid.",
            "COUPON_EXPIRED": "This coupon has expired.",
            "COUPON_EXHAUSTED": "This coupon has reached its usage limit.",
            "COUPON_MINIMUM": "Your order does not reach the coupon minimum.",
        }
        raise HTTPException(status_code=409, detail={"code": code, "message": messages.get(code, "Could not create the order.")})
    await cart_service.clear_cart(db, current_user["user_id"])
    return _ok(result)


@router.get("/orders")
async def list_orders(
    current_user: dict = Depends(require_roles("customer", "admin")),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    customer_id = None if current_user["role"] == "admin" else current_user["user_id"]
    docs, total = await orders_service.list_orders(db, customer_id, page, limit)
    return _ok(docs, {"page": page, "limit": limit, "total": total, "total_pages": max(1, -(-total // limit))})


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    current_user: dict = Depends(require_roles("customer", "admin")),
    db=Depends(get_db),
):
    order = (
        await order_model.find_by_id(db, order_id)
        if current_user["role"] == "admin"
        else await order_model.find_for_customer(db, order_id, current_user["user_id"])
    )
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    return _ok(order)


@router.get("/orders/{order_id}/receipt")
async def download_receipt(
    order_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    """Only the buyer can download a receipt, after delivery and payment confirmation."""
    order = await order_model.find_for_customer(db, order_id, current_user["user_id"])
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if order.get("status") != "delivered" or order.get("payment_status") != "paid":
        raise HTTPException(status_code=409, detail={
            "code": "RECEIPT_NOT_READY",
            "message": "A receipt is available after delivery and payment confirmation.",
        })

    customer = await db.users.find_one(
        {"_id": ObjectId(current_user["user_id"])}, {"name": 1}
    )
    pdf = receipt_service.render_receipt(order, customer.get("name") if customer else None)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="shoply-receipt-{order_id[-8:]}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    """
    Stripe webhook handler. Validates Stripe-Signature before processing.
    Signature verification IS the authentication for this endpoint.
    """
    from app.core.config import settings
    if not settings.ENABLE_ONLINE_PAYMENTS:
        raise HTTPException(status_code=404, detail={"code": "FEATURE_DISABLED"})
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = payment_service.verify_webhook_signature(payload, sig_header)
    except Exception:
        raise HTTPException(status_code=400, detail={"code": "INVALID_SIGNATURE"})

    event_type = event.get("type")
    if event_type == "payment_intent.succeeded":
        pass  # Handled in confirm_order endpoint
    elif event_type == "charge.refunded":
        pass  # TODO: Update order payment_status → refunded

    return {"received": True}
