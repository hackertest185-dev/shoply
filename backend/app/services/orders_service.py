"""services/orders_service.py"""
import secrets

from bson import ObjectId

from app.core.redis_client import store_otp
from app.models import order_model
from app.models import coupon_model
from app.services.audit_log_service import write_audit_log
from app.routers.coupons_router import validate_coupon
from app.services.email_service import email_is_configured, send_order_email


def _generate_otp() -> str:
    """Generate a cryptographically random 4-digit OTP."""
    return str(secrets.randbelow(10000)).zfill(4)


async def create_contact_request(db, customer_id: str, whatsapp_number: str, cart: dict, ip: str, coupon_code: str | None = None) -> dict:
    """Record an unpaid order request; the admin contacts the buyer on WhatsApp."""
    items = [
        {
            "product_id": item["product_id"],
            "variant_id": item.get("variant_id"),
            "name": item["name"],
            "qty": item["qty"],
            "unit_price": item["unit_price"],
        }
        for item in cart["items"]
    ]
    summary = cart["summary"]
    discount = 0.0
    coupon = None
    if coupon_code:
        try:
            coupon = await validate_coupon(db, coupon_code, float(summary["subtotal"]))
            discount = float(coupon["discount"])
        except ValueError as exc:
            raise ValueError(str(exc))
    total = round(max(0, float(summary["total"]) - discount), 2)
    if not await order_model.decrement_stock_atomic(db, items):
        raise ValueError("INSUFFICIENT_STOCK")
    if coupon:
        coupon_doc = await coupon_model.find_by_code(db, coupon["code"])
        if not coupon_doc or not await coupon_model.increment_usage(db, coupon_doc["_id"] if isinstance(coupon_doc.get("_id"), str) else str(coupon_doc["_id"])):
            await order_model.restore_stock(db, items)
            raise ValueError("COUPON_EXHAUSTED")
    order_id = await order_model.insert_order(db, {
        "customer_id": ObjectId(customer_id),
        "delivery_id": None,
        "items": items,
        "items_count": sum(item["qty"] for item in items),
        "whatsapp_number": whatsapp_number,
        "status": "pending_contact",
        "delivery_status": "awaiting_confirmation",
        "payment_status": "unpaid",
        "payment_method": "arrange_with_admin",
        "contact_status": "not_contacted",
        "admin_contacted_at": None,
        "admin_contacted_by": None,
        "subtotal": summary["subtotal"],
        "tax": summary.get("tax_estimate", 0),
        "shipping_cost": 0,
        "discount_amount": discount,
        "coupon_code": coupon["code"] if coupon else None,
        "total": total,
        "stock_reserved": True,
    })
    await write_audit_log(
        db, customer_id, "customer", "order_requested", "orders", order_id,
        {"items_count": len(items), "total": total, "discount": discount}, ip,
    )
    customer = await db.users.find_one({"_id": ObjectId(customer_id)}, {"email": 1, "name": 1})
    if customer and email_is_configured():
        try:
            await send_order_email(customer["email"], "Order request received", f"Hi {customer.get('name', '')}, your Shoply order #{order_id[-8:]} was received. Total: {total:.2f} EGP. We will contact you on WhatsApp.")
        except Exception:
            pass
    return {
        "order_id": order_id,
        "status": "pending_contact",
        "payment_status": "unpaid",
        "total": total,
        "discount_amount": discount,
        "items_count": len(items),
        "message": "Order request received. The store will contact you on WhatsApp.",
    }


async def create_order(
    db,
    customer_id: str,
    payment_intent_id: str,
    address: dict,
    cart_items: list[dict],
    totals: dict,
    ip: str,
) -> dict:
    """
    Create order record atomically, decrement stock, generate OTP.
    Idempotent: if payment_intent_id already exists, return existing order.
    """
    # Idempotency check
    existing = await order_model.find_by_payment_intent(db, payment_intent_id)
    if existing:
        return existing

    # Decrement stock atomically
    stock_ok = await order_model.decrement_stock_atomic(db, cart_items)
    if not stock_ok:
        raise ValueError("INSUFFICIENT_STOCK")

    order_data = {
        "customer_id":         ObjectId(customer_id),
        "delivery_id":         None,
        "items":               cart_items,
        "shipping_address":    address,
        "status":              "confirmed",
        "delivery_status":     "unassigned",
        "otp_generated":       True,
        "proof_of_delivery_url": None,
        "payment_intent_id":   payment_intent_id,
        "payment_status":      "paid",
        "subtotal":            totals["subtotal"],
        "tax":                 totals.get("tax_estimate", totals.get("tax", 0)),
        "shipping_cost":       totals.get("shipping_cost", 0),
        "total":               totals["total"],
    }

    order_id = await order_model.insert_order(db, order_data)

    # Generate OTP and store bcrypt-hashed in Redis
    otp_plain = _generate_otp()
    await store_otp(order_id, otp_plain)

    customer = await db.users.find_one({"_id": ObjectId(customer_id)}, {"email": 1, "name": 1})
    if customer and email_is_configured():
        try:
            await send_order_email(customer["email"], "Order confirmed", f"Hi {customer.get('name', '')}, your Shoply order #{order_id[-8:]} is confirmed. Total: {totals['total']:.2f} EGP.")
        except Exception:
            pass

    await write_audit_log(
        db, customer_id, "customer", "order_created", "orders", order_id,
        {"total": totals["total"], "items_count": len(cart_items)}, ip,
    )

    return {
        "order_id":        order_id,
        "status":          "confirmed",
        "delivery_status": "unassigned",
        "total":           totals["total"],
        "items_count":     len(cart_items),
        "message":         "Order confirmed. Your OTP has been sent to your email.",
    }


async def list_orders(
    db, customer_id: str | None, page: int = 1, limit: int = 20
) -> tuple[list[dict], int]:
    skip = (page - 1) * limit
    query: dict = {}
    if customer_id:
        query["customer_id"] = ObjectId(customer_id)

    cursor = (
        db.orders.find(query, {"otp_generated": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    docs  = await cursor.to_list(length=limit)
    total = await db.orders.count_documents(query)

    return [order_model._serialize(doc) for doc in docs], total
