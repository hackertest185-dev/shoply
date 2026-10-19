import uuid
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_admin, require_customer
from app.models import chat_model
from app.schemas.chat_schema import MessageCreate
from app.services.email_service import email_is_configured, send_order_email

router = APIRouter(tags=["Order chat"])


def _ok(data):
    return {"success": True, "data": data, "request_id": str(uuid.uuid4())}


async def _customer_order(db, order_id: str, user_id: str):
    if not ObjectId.is_valid(order_id):
        return None
    return await db.orders.find_one({"_id": ObjectId(order_id), "customer_id": ObjectId(user_id)})


@router.get("/orders/{order_id}/chat")
async def customer_messages(order_id: str, current_user=Depends(require_customer), db=Depends(get_db)):
    if not await _customer_order(db, order_id, current_user["user_id"]):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})
    return _ok(await chat_model.list_messages(db, order_id))


@router.post("/orders/{order_id}/chat", status_code=201)
async def customer_message(order_id: str, body: MessageCreate, current_user=Depends(require_customer), db=Depends(get_db)):
    order = await _customer_order(db, order_id, current_user["user_id"])
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})
    message = await chat_model.insert_message(db, order_id, current_user["user_id"], current_user["user_id"], "customer", body.text)
    return _ok(message)


@router.get("/admin/orders/{order_id}/chat")
async def admin_messages(order_id: str, current_user=Depends(require_admin), db=Depends(get_db)):
    if not ObjectId.is_valid(order_id) or not await db.orders.find_one({"_id": ObjectId(order_id)}, {"_id": 1}):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})
    return _ok(await chat_model.list_messages(db, order_id))


@router.post("/admin/orders/{order_id}/chat", status_code=201)
async def admin_message(order_id: str, body: MessageCreate, current_user=Depends(require_admin), db=Depends(get_db)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})
    order = await db.orders.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found."})
    message = await chat_model.insert_message(db, order_id, str(order["customer_id"]), current_user["user_id"], "admin", body.text)
    customer = await db.users.find_one({"_id": order["customer_id"]}, {"email": 1})
    if customer and email_is_configured():
        try:
            await send_order_email(customer["email"], f"Shoply order #{order_id[-8:]} message", f"The Shoply team replied to your order chat:\n\n{body.text}")
        except Exception:
            pass
    return _ok(message)
