"""services/admin_service.py"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


CAIRO = ZoneInfo("Africa/Cairo")


async def get_dashboard_kpis(db) -> dict:
    """Aggregate KPIs for admin dashboard."""
    today_start = datetime.combine(datetime.now(CAIRO).date(), time.min, tzinfo=CAIRO).astimezone(timezone.utc)

    revenue_pipeline = [
        {"$match": {"status": "delivered", "payment_status": "paid", "delivered_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    revenue_result = await db.orders.aggregate(revenue_pipeline).to_list(1)
    revenue_today  = revenue_result[0]["total"] if revenue_result else 0.0

    orders_today   = await db.orders.count_documents({"created_at": {"$gte": today_start}})
    new_users      = await db.users.count_documents({"created_at": {"$gte": today_start}})
    pending_agents = await db.users.count_documents({"verification_status": {"$eq": "pending"}})
    total_orders   = await db.orders.count_documents({})
    total_users    = await db.users.count_documents({})
    total_vendors  = await db.users.count_documents({"role": {"$eq": "vendor"}})
    approved_agents = await db.users.count_documents({"role": {"$eq": "delivery"}, "verification_status": {"$eq": "approved"}})
    unassigned_orders = await db.orders.count_documents({"delivery_status": {"$eq": "unassigned"}})
    delivered_orders  = await db.orders.count_documents({"status": {"$eq": "delivered"}})

    return {
        "revenue_today":       revenue_today,
        "orders_today":        orders_today,
        "new_users":           new_users,
        "pending_reviews":     pending_agents,
        "total_orders":        total_orders,
        "total_users":         total_users,
        "total_vendors":       total_vendors,
        "approved_agents":     approved_agents,
        "unassigned_orders":   unassigned_orders,
        "delivered_orders":    delivered_orders,
        "error_rate":          0.0,
        "p95_latency":         0,
    }


async def get_sales_summary(db, days: int = 14) -> dict:
    """Count only paid, delivered orders as sales; group recent sales by delivery day."""
    today = datetime.now(CAIRO).date()
    start_day = today - timedelta(days=days - 1)
    start = datetime.combine(start_day, time.min, tzinfo=CAIRO).astimezone(timezone.utc)
    sales_filter = {"status": "delivered", "payment_status": "paid"}
    lifetime = await db.orders.aggregate([
        {"$match": sales_filter},
        {"$group": {
            "_id": None,
            "revenue": {"$sum": "$total"},
            "orders": {"$sum": 1},
            "items": {"$sum": "$items_count"},
        }},
    ]).to_list(1)
    totals = lifetime[0] if lifetime else {}

    daily = {
        (start_day + timedelta(days=offset)).isoformat(): {
            "date": (start_day + timedelta(days=offset)).isoformat(),
            "revenue": 0.0,
            "orders": 0,
            "items": 0,
        }
        for offset in range(days)
    }
    cursor = db.orders.find(
        {**sales_filter, "delivered_at": {"$gte": start}},
        {"total": 1, "items_count": 1, "delivered_at": 1},
    )
    async for order in cursor:
        delivered_at = order["delivered_at"]
        if delivered_at.tzinfo is None:
            delivered_at = delivered_at.replace(tzinfo=timezone.utc)
        day = delivered_at.astimezone(CAIRO).date().isoformat()
        if day in daily:
            daily[day]["revenue"] += float(order.get("total") or 0)
            daily[day]["orders"] += 1
            daily[day]["items"] += int(order.get("items_count") or 0)

    for row in daily.values():
        row["revenue"] = round(row["revenue"], 2)
    count = int(totals.get("orders") or 0)
    revenue = round(float(totals.get("revenue") or 0), 2)
    return {
        "currency": "EGP",
        "delivered_orders": count,
        "items_sold": int(totals.get("items") or 0),
        "total_revenue": revenue,
        "average_order_value": round(revenue / count, 2) if count else 0.0,
        "period_days": days,
        "period_revenue": round(sum(row["revenue"] for row in daily.values()), 2),
        "daily": list(daily.values()),
    }


async def get_audit_logs(
    db, actor_id: str | None, action: str | None,
    from_dt: datetime | None, to_dt: datetime | None,
    page: int, limit: int
) -> tuple[list[dict], int]:
    query: dict = {}
    if actor_id:
        query["actor_id"] = {"$eq": actor_id}
    if action and action != "all":
        query["action"] = {"$eq": action}
    if from_dt or to_dt:
        dt_filter: dict = {}
        if from_dt:
            dt_filter["$gte"] = from_dt
        if to_dt:
            dt_filter["$lte"] = to_dt
        query["created_at"] = dt_filter

    skip   = (page - 1) * limit
    cursor = db.audit_logs.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs   = await cursor.to_list(length=limit)
    total  = await db.audit_logs.count_documents(query)

    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()

    return docs, total
