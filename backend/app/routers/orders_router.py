"""routers/orders_router.py"""
import asyncio
import uuid
import re
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_customer, require_roles
from app.schemas.order_schema import OrderRequest
from app.services import cart_service, orders_service, payment_service, receipt_service, push_notification_service
from app.models import order_model
from app.routers.coupons_router import validate_coupon

router = APIRouter(tags=["Orders & Checkout"])


def _paymob_enabled(settings) -> bool:
    return bool(
        settings.ENABLE_ONLINE_PAYMENTS
        and settings.PAYMOB_SECRET_KEY
        and settings.PAYMOB_PUBLIC_KEY
        and settings.PAYMOB_CARD_INTEGRATION_ID > 0
        and settings.PAYMOB_HMAC_SECRET
    )


@router.get("/payments/paymob/status")
async def paymob_status():
    from app.core.config import settings
    return _ok({"card_checkout_enabled": _paymob_enabled(settings)})


def _paymob_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _verify_paymob_hmac(obj: dict, signature: str, secret: str) -> bool:
    """Verify Paymob's documented ordered transaction HMAC (SHA-512)."""
    source = obj.get("source_data") or {}
    order = obj.get("order") or {}
    fields = (
        obj.get("amount_cents"), obj.get("created_at"), obj.get("currency"),
        obj.get("error_occured"), obj.get("has_parent_transaction"), obj.get("id"),
        obj.get("integration_id"), obj.get("is_3d_secure"), obj.get("is_auth"),
        obj.get("is_capture"), obj.get("is_refunded"), obj.get("is_standalone_payment"),
        obj.get("is_voided"), order.get("id"), obj.get("owner"), obj.get("pending"),
        source.get("pan"), source.get("sub_type"), source.get("type"), obj.get("success"),
    )
    message = "".join(_paymob_value(value) for value in fields).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha512).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature.lower())


def _paymob_post_intention(settings, payload: dict) -> dict:
    url = settings.PAYMOB_API_BASE_URL.rstrip("/") + "/v1/intention/"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Token {settings.PAYMOB_SECRET_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read(1024 * 1024))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ValueError("PAYMOB_UNAVAILABLE") from exc
    if not isinstance(result, dict) or not result.get("client_secret"):
        raise ValueError("PAYMOB_REJECTED")
    return result


def _ok(data, meta=None, code=200) -> dict:
    r = {"success": True, "data": data, "request_id": str(uuid.uuid4())}
    if meta:
        r["meta"] = meta
    return r


@router.post("/orders", status_code=201)
async def request_order(
    body: OrderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
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
    background_tasks.add_task(
        push_notification_service.send_new_order_notification,
        result["order_id"],
    )
    return _ok(result)


@router.post("/payments/paymob/checkout", status_code=201)
async def create_paymob_checkout(
    body: OrderRequest,
    request: Request,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    """Create a Paymob hosted card checkout from server-priced cart data."""
    from app.core.config import settings
    if not _paymob_enabled(settings):
        raise HTTPException(status_code=503, detail={"code": "PAYMENTS_NOT_CONFIGURED", "message": "Card payments are not available yet."})

    idempotency_key = request.headers.get("Idempotency-Key", "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", idempotency_key):
        raise HTTPException(status_code=422, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
    existing = await db.orders.find_one({
        "customer_id": ObjectId(current_user["user_id"]),
        "idempotency_key": idempotency_key,
    })
    if existing:
        if existing.get("status") == "pending_payment" and existing.get("paymob_checkout_url"):
            return _ok({"checkout_url": existing["paymob_checkout_url"], "order_id": str(existing["_id"])})
        raise HTTPException(status_code=409, detail={"code": "CHECKOUT_ALREADY_STARTED", "message": "This checkout request was already processed. Start checkout again from your cart."})

    # Release stock reserved by abandoned checkouts before checking availability.
    expired = await db.orders.find({
        "status": "pending_payment",
        "created_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=30)},
        "stock_reserved": True,
    }).limit(100).to_list(100)
    for stale in expired:
        changed = await db.orders.update_one(
            {"_id": stale["_id"], "status": "pending_payment", "stock_reserved": True},
            {"$set": {"status": "cancelled", "payment_status": "expired", "stock_reserved": False, "updated_at": datetime.now(timezone.utc)}},
        )
        if changed.modified_count:
            await order_model.restore_stock(db, stale.get("items", []))

    cart = await cart_service.get_cart_with_prices(db, current_user["user_id"])
    if not cart["items"]:
        raise HTTPException(status_code=400, detail={"code": "CART_EMPTY", "message": "Cart is empty."})
    if cart["warnings"] or any(not item["in_stock"] for item in cart["items"]):
        raise HTTPException(status_code=409, detail={"code": "CART_UNAVAILABLE", "message": "Update your cart before ordering."})

    discount = 0.0
    coupon = None
    if body.coupon_code:
        try:
            coupon = await validate_coupon(db, body.coupon_code, float(cart["summary"]["subtotal"]))
            discount = float(coupon["discount"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": str(exc), "message": "This coupon cannot be applied."}) from exc
    total = round(max(0, float(cart["summary"]["total"]) - discount), 2)
    amount_cents = int(round(total * 100))
    if amount_cents < 100:
        raise HTTPException(status_code=400, detail={"code": "INVALID_AMOUNT", "message": "The payment amount must be at least EGP 1."})

    customer = await db.users.find_one({"_id": ObjectId(current_user["user_id"])}, {"email": 1, "name": 1}) or {}
    order_items = [{
        "product_id": item["product_id"], "variant_id": item.get("variant_id"),
        "name": item["name"], "qty": item["qty"], "unit_price": item["unit_price"],
    } for item in cart["items"]]
    if not await order_model.decrement_stock_atomic(db, order_items):
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_STOCK", "message": "An item just sold out. Refresh your cart."})

    order_id = str(ObjectId())
    now = datetime.now(timezone.utc)
    order_data = {
        "_id": ObjectId(order_id), "customer_id": ObjectId(current_user["user_id"]),
        "delivery_id": None, "items": order_items,
        "items_count": sum(item["qty"] for item in order_items),
        "whatsapp_number": body.whatsapp_number,
        "status": "pending_payment", "delivery_status": "awaiting_confirmation",
        "payment_status": "pending", "payment_method": "paymob",
        "contact_status": "not_contacted", "admin_contacted_at": None,
        "admin_contacted_by": None, "subtotal": cart["summary"]["subtotal"],
        "tax": 0, "shipping_cost": 0, "discount_amount": discount,
        "coupon_code": coupon["code"] if coupon else None, "total": total,
        "stock_reserved": True, "idempotency_key": idempotency_key,
        "paymob_reference": order_id, "created_at": now, "updated_at": now,
        "status_history": [{"status": "pending_payment", "at": now, "by": ObjectId(current_user["user_id"])}],
    }
    try:
        await db.orders.insert_one(order_data)
    except DuplicateKeyError as exc:
        await order_model.restore_stock(db, order_items)
        raise HTTPException(status_code=409, detail={"code": "CHECKOUT_ALREADY_STARTED", "message": "This checkout request was already processed. Please try again."}) from exc
    except Exception:
        await order_model.restore_stock(db, order_items)
        raise

    name_parts = str(customer.get("name") or "Shoply customer").strip().split(maxsplit=1)
    billing_data = {
        "apartment": "NA", "first_name": name_parts[0][:50],
        "last_name": (name_parts[1] if len(name_parts) > 1 else "Customer")[:50],
        "street": "NA", "building": "NA", "floor": "NA",
        "phone_number": body.whatsapp_number, "city": "Cairo", "country": "EG",
        "email": str(customer.get("email") or "").strip().lower(), "state": "Cairo",
    }
    payload = {
        "amount": amount_cents, "currency": "EGP",
        "payment_methods": [settings.PAYMOB_CARD_INTEGRATION_ID],
        "billing_data": billing_data,
        "special_reference": order_id,
        "expiration": 1800,
        "notification_url": settings.FRONTEND_URL.rstrip("/") + "/api/v1/payments/paymob/webhook",
        "redirection_url": settings.FRONTEND_URL.rstrip("/") + "/?payment=paymob&order_id=" + order_id,
        "extras": {"shoply_order_id": order_id},
    }
    try:
        intention = await asyncio.to_thread(_paymob_post_intention, settings, payload)
    except ValueError as exc:
        changed = await db.orders.update_one({"_id": ObjectId(order_id), "status": "pending_payment", "stock_reserved": True}, {"$set": {"status": "cancelled", "payment_status": "failed", "stock_reserved": False, "updated_at": datetime.now(timezone.utc)}})
        if changed.modified_count:
            await order_model.restore_stock(db, order_items)
        raise HTTPException(status_code=502, detail={"code": str(exc), "message": "Could not start the secure payment. Please try again."}) from exc

    checkout_url = (
        settings.PAYMOB_CHECKOUT_URL.rstrip("/") + "/?publicKey="
        + quote(settings.PAYMOB_PUBLIC_KEY, safe="")
        + "&clientSecret="
        + quote(intention["client_secret"], safe="")
    )
    await db.orders.update_one(
        {"_id": ObjectId(order_id), "status": "pending_payment"},
        {"$set": {"paymob_intention_id": str(intention.get("id", "")), "paymob_checkout_url": checkout_url, "updated_at": datetime.now(timezone.utc)}},
    )
    return _ok({"checkout_url": checkout_url, "order_id": order_id, "amount": total, "currency": "EGP"}, code=201)


@router.post("/payments/paymob/webhook")
async def paymob_webhook(request: Request, db=Depends(get_db)):
    """Accept only authentic Paymob events and atomically confirm payment."""
    from app.core.config import settings
    if not _paymob_enabled(settings):
        raise HTTPException(status_code=404, detail={"code": "FEATURE_DISABLED"})
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CALLBACK"}) from exc
    obj = payload.get("obj") if isinstance(payload, dict) else None
    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail={"code": "INVALID_CALLBACK"})
    signature = request.query_params.get("hmac") or payload.get("hmac") or obj.get("hmac") or ""
    if not _verify_paymob_hmac(obj, signature, settings.PAYMOB_HMAC_SECRET):
        raise HTTPException(status_code=400, detail={"code": "INVALID_SIGNATURE"})
    if str(obj.get("integration_id")) != str(settings.PAYMOB_CARD_INTEGRATION_ID):
        raise HTTPException(status_code=400, detail={"code": "INVALID_INTEGRATION"})
    order_info = obj.get("order") or {}
    claims = obj.get("payment_key_claims") or {}
    reference = obj.get("special_reference") or obj.get("merchant_order_id") or order_info.get("merchant_order_id") or claims.get("special_reference") or (claims.get("extras") or {}).get("shoply_order_id") or (claims.get("extra") or {}).get("shoply_order_id")
    if not isinstance(reference, str) or not ObjectId.is_valid(reference):
        raise HTTPException(status_code=400, detail={"code": "UNKNOWN_ORDER"})
    order = await db.orders.find_one({"_id": ObjectId(reference), "paymob_reference": reference})
    if not order:
        raise HTTPException(status_code=404, detail={"code": "UNKNOWN_ORDER"})
    expected_cents = int(round(float(order.get("total", 0)) * 100))
    try:
        received_cents = int(obj.get("amount_cents", -1))
    except (TypeError, ValueError):
        received_cents = -1
    if str(obj.get("currency", "")).upper() != "EGP" or received_cents != expected_cents:
        raise HTTPException(status_code=400, detail={"code": "PAYMENT_MISMATCH"})

    successful = (
        obj.get("success") is True and obj.get("pending") is False
        and obj.get("error_occured") is False and obj.get("is_refunded") is False
        and obj.get("is_voided") is False
    )
    now = datetime.now(timezone.utc)
    if successful:
        updated = await db.orders.find_one_and_update(
            {"_id": order["_id"], "status": "pending_payment", "payment_status": "pending", "paymob_reference": reference},
            {"$set": {
                "status": "pending_contact", "delivery_status": "awaiting_confirmation",
                "payment_status": "paid", "payment_confirmed_at": now,
                "paymob_transaction_id": str(obj.get("id", "")), "stock_reserved": False,
                "updated_at": now,
            }, "$push": {"status_history": {"status": "pending_contact", "at": now}}},
            return_document=True,
        )
        if updated:
            await db.carts.update_one(
                {"user_id": str(updated["customer_id"])},
                {"$set": {"items": [], "updated_at": now}},
            )
            if updated.get("coupon_code"):
                from app.models import coupon_model
                coupon_doc = await coupon_model.find_by_code(db, updated["coupon_code"])
                if coupon_doc:
                    await coupon_model.increment_usage(db, str(coupon_doc["_id"]))
            try:
                await push_notification_service.send_new_order_notification(reference)
            except Exception:
                pass
        elif order.get("payment_status") != "paid":
            # Do not acknowledge a paid transaction that cannot be correlated and
            # transitioned; Paymob can retry its callback after this server error.
            raise HTTPException(status_code=409, detail={"code": "ORDER_STATE_CONFLICT"})
    else:
        changed = await db.orders.update_one(
            {"_id": order["_id"], "status": "pending_payment", "payment_status": "pending", "stock_reserved": True},
            {"$set": {"status": "cancelled", "payment_status": "failed", "stock_reserved": False, "updated_at": now}},
        )
        if changed.modified_count:
            await order_model.restore_stock(db, order.get("items", []))
    return {"received": True}


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
