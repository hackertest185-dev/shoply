"""routers/admin_router.py"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from bson import ObjectId
from pymongo import ReturnDocument

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_admin
from app.schemas.admin_schema import CompleteDeliveryRequest, ProductRejectRequest, RefundRequest, UserStatusUpdate, OrderAssignRequest
from app.schemas.delivery_schema import AgentRejectRequest
from app.services import admin_service, verification_service
from app.services.audit_log_service import write_audit_log
from datetime import datetime, timezone

router = APIRouter(prefix="/admin", tags=["Admin"])


def _ok(data, meta=None) -> dict:
    r = {"success": True, "data": data, "request_id": str(uuid.uuid4())}
    if meta:
        r["meta"] = meta
    return r


@router.get("/dashboard")
async def dashboard(
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    kpis = await admin_service.get_dashboard_kpis(db)
    return _ok(kpis)


@router.get("/sales/summary")
async def sales_summary(
    days: int = Query(14, ge=7, le=30),
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Admin-only sales totals and a daily chart based on paid, delivered orders."""
    return _ok(await admin_service.get_sales_summary(db, days))


@router.get("/orders")
async def list_all_orders(
    status: str | None = None,
    delivery_status: str | None = None,
    payment_status: str | None = None,
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """List all orders with optional filters. Admin only."""
    query: dict = {}
    if status:
        query["status"] = {"$eq": status}
    if delivery_status:
        query["delivery_status"] = {"$eq": delivery_status}
    if payment_status:
        query["payment_status"] = {"$eq": payment_status}

    skip = (page - 1) * limit
    cursor = (
        db.orders.find(query, {"otp_generated": 0})
        .sort("delivered_at" if status == "delivered" else "created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    total = await db.orders.count_documents(query)

    from app.models import order_model
    return _ok([order_model._serialize(doc) for doc in docs], {
        "page": page, "limit": limit, "total": total,
        "total_pages": max(1, -(-total // limit)),
    })


@router.get("/orders/{order_id}")
async def get_order_admin(
    order_id: str,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Get single order detail. Admin only."""
    from app.models import order_model
    try:
        order = await order_model.find_by_id(db, order_id)
    except Exception:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok(order)


@router.post("/orders/{order_id}/whatsapp-contacted")
async def mark_whatsapp_contacted(
    order_id: str,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Record the admin's confirmation that the WhatsApp message was sent."""
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    contacted_at = datetime.now(timezone.utc)
    order = await db.orders.find_one_and_update(
        {"_id": ObjectId(order_id), "status": "pending_contact", "contact_status": {"$ne": "contacted"}},
        {"$set": {
            "contact_status": "contacted",
            "admin_contacted_at": contacted_at,
            "admin_contacted_by": current_user["user_id"],
            "updated_at": contacted_at,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not order:
        exists = await db.orders.find_one({"_id": ObjectId(order_id)}, {"_id": 1})
        raise HTTPException(
            status_code=409 if exists else 404,
            detail={"code": "CONFLICT" if exists else "NOT_FOUND",
                    "message": "Only pending requests can be contacted."},
        )
    await write_audit_log(
        db,
        current_user["user_id"],
        "admin",
        "whatsapp_contacted",
        "orders",
        order_id,
        {"whatsapp_number": order.get("whatsapp_number")},
        request.client.host if request.client else None,
    )
    return _ok({
        "order_id": order_id,
        "contact_status": "contacted",
        "contacted_at": contacted_at.isoformat(),
    })


@router.post("/orders/{order_id}/deliver")
async def complete_delivery(
    order_id: str,
    body: CompleteDeliveryRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Record an InstaPay payment and delivery once, using an atomic state transition."""
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    now = datetime.now(timezone.utc)
    order = await db.orders.find_one_and_update(
        {
            "_id": ObjectId(order_id),
            "status": "pending_contact",
            "delivery_status": "awaiting_confirmation",
            "contact_status": "contacted",
            "payment_status": "unpaid",
        },
        {"$set": {
            "status": "delivered",
            "delivery_status": "delivered",
            "payment_status": "paid",
            "payment_method": "instapay",
            "payment_confirmed_at": now,
            "delivered_at": now,
            "delivered_by": current_user["user_id"],
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not order:
        exists = await db.orders.find_one({"_id": ObjectId(order_id)}, {"_id": 1})
        raise HTTPException(
            status_code=409 if exists else 404,
            detail={"code": "CONFLICT" if exists else "NOT_FOUND",
                    "message": "Only contacted, unpaid requests can be marked delivered."},
        )
    await write_audit_log(
        db, current_user["user_id"], "admin", "order_delivered",
        "orders", order_id, {"total": order.get("total"), "payment_method": "instapay"},
        request.client.host if request.client else None,
    )
    return _ok({
        "order_id": order_id,
        "status": "delivered",
        "payment_status": "paid",
        "delivered_at": now.isoformat(),
    })


@router.post("/orders/{order_id}/assign")
async def assign_delivery_agent(
    order_id: str,
    body: OrderAssignRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Assign a delivery agent to an order. Only orders in 'unassigned' status can be assigned."""
    from app.models import order_model, user_model

    order = await order_model.find_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    if order.get("delivery_status") not in ("unassigned", "assigned"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": "Order is already in delivery progress or completed."},
        )

    delivery_agent = await user_model.find_by_id(db, body.delivery_id)
    if not delivery_agent:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Delivery agent not found."})
    if delivery_agent.get("role") != "delivery":
        raise HTTPException(status_code=400, detail={"code": "INVALID_ROLE", "message": "User is not a delivery agent."})
    if delivery_agent.get("verification_status") != "approved":
        raise HTTPException(status_code=400, detail={"code": "NOT_VERIFIED", "message": "Delivery agent is not verified."})

    new_status = "confirmed" if order.get("status") == "confirmed" else order.get("status", "confirmed")

    await order_model.update_order_status(
        db, order_id,
        status=new_status,
        delivery_status="assigned",
        extra={"delivery_id": ObjectId(body.delivery_id)},
    )

    await write_audit_log(
        db, current_user["user_id"], "admin", "order_assigned",
        "orders", order_id, {"delivery_id": body.delivery_id},
        request.client.host if request.client else None,
    )

    return _ok({
        "message": "Delivery agent assigned successfully.",
        "order_id": order_id,
        "delivery_id": body.delivery_id,
        "delivery_status": "assigned",
    })


@router.post("/orders/{order_id}/cancel")
async def cancel_order_admin(
    order_id: str,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Cancel an order. Only orders not yet delivered can be cancelled."""
    from app.models import order_model

    order = await order_model.find_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    if order.get("status") in ("delivered", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": f"Order cannot be cancelled (current status: {order.get('status')})."},
        )

    await order_model.update_order_status(
        db, order_id,
        status="cancelled",
        delivery_status="cancelled",
    )

    await write_audit_log(
        db, current_user["user_id"], "admin", "order_cancelled",
        "orders", order_id, {},
        request.client.host if request.client else None,
    )

    return _ok({"message": "Order cancelled.", "order_id": order_id, "status": "cancelled"})


@router.get("/users")
async def list_users(
    current_user: dict = Depends(require_admin),
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    role:  str | None = None,
    db=Depends(get_db),
):
    query: dict = {}
    if role:
        query["role"] = {"$eq": role}
    skip   = (page - 1) * limit
    cursor = db.users.find(query, {"password_hash": 0}).skip(skip).limit(limit)
    docs   = await cursor.to_list(limit)
    total  = await db.users.count_documents(query)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return _ok(docs, {"page": page, "total": total})


@router.patch("/users/{user_id}")
async def update_user_status(
    user_id: str,
    body: UserStatusUpdate,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.models import user_model
    await user_model.update_user(db, user_id, {"status": body.status})
    await write_audit_log(
        db, current_user["user_id"], "admin", "user_status_changed",
        "users", user_id, {"status": body.status},
        request.client.host if request.client else None,
    )
    return _ok({"message": "User status updated."})


@router.patch("/products/{product_id}/approve")
async def approve_product(
    product_id: str,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.models import product_model
    await product_model.update_product(db, product_id, {"status": "active"})
    await write_audit_log(
        db, current_user["user_id"], "admin", "product_approved",
        "products", product_id, {}, request.client.host if request.client else None,
    )
    return _ok({"message": "Product approved and now active."})


@router.patch("/products/{product_id}/reject")
async def reject_product(
    product_id: str,
    body: ProductRejectRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.models import product_model
    await product_model.update_product(db, product_id, {"status": "inactive", "rejection_reason": body.reason})
    await write_audit_log(
        db, current_user["user_id"], "admin", "product_rejected",
        "products", product_id, {"reason": body.reason},
        request.client.host if request.client else None,
    )
    return _ok({"message": "Product rejected."})


@router.get("/products/pending")
async def pending_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """
    List products awaiting review (status=pending_review).
    """
    skip = (page - 1) * limit
    cursor = db.products.find({"status": {"$eq": "pending_review"}}).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    total = await db.products.count_documents({"status": {"$eq": "pending_review"}})

    # Reuse product serializer + enrichment logic
    from app.models.product_model import _serialize
    from app.services.products_service import _enrich_products

    items = [_serialize(d) for d in docs]
    items = await _enrich_products(db, items)
    return _ok(items, {"page": page, "total": total})


@router.get("/delivery-agents")
async def list_delivery_agents(
    verification_status: str | None = None,
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    query: dict = {"role": {"$eq": "delivery"}}
    if verification_status and verification_status != "all":
        query["verification_status"] = {"$eq": verification_status}
    skip   = (page - 1) * limit
    cursor = db.users.find(query, {"password_hash": 0}).skip(skip).limit(limit)
    docs   = await cursor.to_list(limit)
    total  = await db.users.count_documents(query)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return _ok(docs, {"page": page, "total": total})


@router.get("/delivery-agents/{agent_id}/documents")
async def get_agent_documents(
    agent_id: str,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    docs = await verification_service.get_agent_documents_with_signed_urls(
        db, agent_id, current_user["user_id"]
    )
    return _ok(docs)


@router.patch("/delivery-agents/{agent_id}/approve")
async def approve_delivery_agent(
    agent_id: str,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    ip = request.client.host if request.client else None
    await verification_service.approve_agent(db, agent_id, current_user["user_id"], ip)
    return _ok({"message": "Delivery agent approved."})


@router.patch("/delivery-agents/{agent_id}/reject")
async def reject_delivery_agent(
    agent_id: str,
    body: AgentRejectRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    ip = request.client.host if request.client else None
    await verification_service.reject_agent(
        db, agent_id, current_user["user_id"], body.rejection_reason, ip
    )
    return _ok({"message": "Delivery agent rejected."})


@router.get("/audit-logs")
async def get_audit_logs(
    actor_id: str | None = None,
    action:   str | None = None,
    page:     int = Query(1, ge=1),
    limit:    int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    docs, total = await admin_service.get_audit_logs(
        db, actor_id, action, None, None, page, limit
    )
    return _ok(docs, {"page": page, "total": total})


@router.get("/monitoring/health")
async def health(
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.core.redis_client import get_redis
    db_ok = False
    redis_ok = False
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        pass
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        pass
    return _ok({
        "mongodb": "connected" if db_ok else "error",
        "redis":   "connected" if redis_ok else "error",
        "status":  "healthy" if (db_ok and redis_ok) else "degraded",
    })


@router.post("/orders/{order_id}/refund")
async def issue_refund(
    order_id: str,
    body: RefundRequest,
    request: Request,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.core.config import settings
    if not settings.ENABLE_ONLINE_PAYMENTS:
        raise HTTPException(status_code=404, detail={"code": "FEATURE_DISABLED"})
    from app.models.order_model import find_by_id
    from app.services.payment_service import create_refund

    order = await find_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    refund = await create_refund(order["payment_intent_id"], body.amount_cents)
    await write_audit_log(
        db, current_user["user_id"], "admin", "refund_issued",
        "orders", order_id, {"amount_cents": body.amount_cents, "reason": body.reason},
        request.client.host if request.client else None,
    )
    return _ok(refund)
