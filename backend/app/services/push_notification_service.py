"""Admin-only web push notifications for new customer orders."""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)
_firebase_app = None


def _get_firebase_app():
    """Initialize Firebase lazily so the API still works before FCM is configured."""
    global _firebase_app
    if not settings.FCM_SERVICE_ACCOUNT_JSON:
        return None
    if _firebase_app is not None:
        return _firebase_app

    import firebase_admin
    from firebase_admin import credentials

    try:
        _firebase_app = firebase_admin.get_app("shoply-push")
    except ValueError:
        service_account = json.loads(settings.FCM_SERVICE_ACCOUNT_JSON)
        _firebase_app = firebase_admin.initialize_app(
            credentials.Certificate(service_account),
            name="shoply-push",
        )
    return _firebase_app


async def send_new_order_notification(order_id: str) -> None:
    """Notify registered admin devices after an order has been committed."""
    if not settings.FCM_SERVICE_ACCOUNT_JSON:
        return
    if not ObjectId.is_valid(order_id):
        return

    try:
        app = _get_firebase_app()
        from firebase_admin import messaging

        db = get_db()
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not order:
            return
        admins = await db.users.find(
            {"role": "admin", "status": {"$in": ["active", None]}},
            {"_id": 1},
        ).to_list(length=100)
        admin_ids = [str(user["_id"]) for user in admins]
        if not admin_ids:
            return
        devices = await db.admin_push_devices.find(
            {"user_id": {"$in": admin_ids}},
            {"token": 1, "token_hash": 1},
        ).to_list(length=500)
        if not devices:
            return

        order_suffix = str(order["_id"])[-8:]
        amount = float(order.get("total") or 0)
        message_data = {
            "type": "new_order",
            "order_id": str(order["_id"]),
        }
        notification = messaging.Notification(
            title="Shoply: طلب جديد",
            body=f"طلب #{order_suffix} جديد بقيمة {amount:,.2f} EGP",
        )

        # FCM's SDK is synchronous; keep network calls off the event loop.
        results = await asyncio.gather(*[
            asyncio.to_thread(
                messaging.send,
                messaging.Message(
                    token=device["token"],
                    notification=notification,
                    data=message_data,
                    webpush=messaging.WebpushConfig(
                        fcm_options=messaging.WebpushFCMOptions(link=settings.FRONTEND_URL),
                    ),
                ),
                app=app,
            )
            for device in devices
        ], return_exceptions=True)

        stale_hashes = []
        for device, result in zip(devices, results):
            if isinstance(result, Exception):
                error_code = str(getattr(result, "code", ""))
                if error_code.endswith(("registration-token-not-registered", "invalid-registration-token")):
                    stale_hashes.append(device["token_hash"])
                else:
                    logger.warning("FCM send failed, type=%s", type(result).__name__)
        if stale_hashes:
            await db.admin_push_devices.delete_many({"token_hash": {"$in": stale_hashes}})
    except Exception as exc:
        # Push is a best-effort side effect and must never affect order creation.
        logger.warning("New-order push unavailable, type=%s", type(exc).__name__)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def register_admin_device(db, admin_id: str, token: str) -> None:
    digest = token_digest(token)
    now = datetime.now(timezone.utc)
    await db.admin_push_devices.update_one(
        {"token_hash": digest},
        {"$set": {"user_id": admin_id, "token": token, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


async def remove_admin_device(db, admin_id: str, token: str) -> None:
    await db.admin_push_devices.delete_one(
        {"user_id": admin_id, "token_hash": token_digest(token)},
    )
