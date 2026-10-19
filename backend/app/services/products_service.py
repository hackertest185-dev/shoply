"""services/products_service.py"""
import uuid

import bleach
from bson import ObjectId

from app.models import product_model
from app.services.audit_log_service import write_audit_log

ALLOWED_HTML_TAGS = ["b", "i", "ul", "ol", "li", "a", "p", "br", "strong", "em"]
ALLOWED_ATTRS = {"a": ["href"]}


def _sanitize_description(raw: str) -> str:
    return bleach.clean(raw, tags=ALLOWED_HTML_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def _build_filters(params: dict) -> dict:
    """Build a safe MongoDB filter dict from query parameters."""
    filters: dict = {"status": {"$eq": "active"}}

    if q := params.get("q"):
        # Text search — uses the text index; sanitized by $text operator
        filters["$text"] = {"$search": str(q)[:100]}

    if category_id := params.get("category"):
        try:
            filters["category_id"] = ObjectId(category_id)
        except Exception:
            pass  # Invalid ObjectId — ignore filter

    if vendor_id := params.get("vendor_id"):
        try:
            filters["vendor_id"] = ObjectId(vendor_id)
        except Exception:
            pass

    price_filter: dict = {}
    if min_p := params.get("min_price"):
        try:
            price_filter["$gte"] = float(min_p)
        except ValueError:
            pass
    if max_p := params.get("max_price"):
        try:
            price_filter["$lte"] = float(max_p)
        except ValueError:
            pass
    if price_filter:
        filters["final_price"] = price_filter

    if params.get("in_stock") in (True, "true", "1"):
        filters["variants.stock_qty"] = {"$gt": 0}

    return filters


def _parse_sort(sort_str: str) -> tuple[str, int]:
    if sort_str.startswith("-"):
        return sort_str[1:], -1
    return sort_str, 1


async def list_products(db, params: dict) -> tuple[list[dict], int]:
    page  = max(1, int(params.get("page", 1)))
    limit = min(100, max(1, int(params.get("limit", 20))))
    skip  = (page - 1) * limit
    sort_field, sort_dir = _parse_sort(params.get("sort", "-created_at"))
    filters = _build_filters(params)
    items, total = await product_model.list_products(db, filters, skip, limit, sort_field, sort_dir)
    return await _enrich_products(db, items), total


async def get_product(db, product_id: str) -> dict | None:
    try:
        ObjectId(product_id)
    except Exception:
        return None
    product = await product_model.find_by_id(db, product_id)
    if not product or product.get("status") != "active":
        return None
    enriched = await _enrich_products(db, [product])
    return enriched[0] if enriched else None


async def _enrich_products(db, products: list[dict]) -> list[dict]:
    """
    Attach lightweight `category` and `vendor` objects for UI.
    Keeps schema backward compatible (still includes category_id/vendor_id too).
    """
    if not products:
        return products

    cat_ids = {p.get("category_id") for p in products if p.get("category_id")}
    ven_ids = {p.get("vendor_id") for p in products if p.get("vendor_id")}

    categories = {}
    if cat_ids:
        docs = await db.categories.find({"_id": {"$in": [ObjectId(cid) for cid in cat_ids if len(str(cid)) == 24]}}, {"name": 1}).to_list(length=1000)
        for d in docs:
            categories[str(d["_id"])] = {"id": str(d["_id"]), "name": d.get("name")}

    vendors = {}
    if ven_ids:
        docs = await db.users.find({"_id": {"$in": [ObjectId(vid) for vid in ven_ids if len(str(vid)) == 24]}}, {"name": 1}).to_list(length=1000)
        for d in docs:
            vendors[str(d["_id"])] = {"id": str(d["_id"]), "name": d.get("name")}

    for p in products:
        if p.get("category_id"):
            p["category"] = categories.get(str(p["category_id"]))
        if p.get("vendor_id"):
            p["vendor"] = vendors.get(str(p["vendor_id"]))
        # Compute in_stock from variants so the frontend can use it directly.
        # Products with no variants have untracked stock → always available.
        variants = p.get("variants", [])
        p["in_stock"] = any(v.get("stock_qty", 0) > 0 for v in variants) if variants else True
    return products


async def create_product(db, admin_id: str, data: dict) -> str:
    data["description"] = _sanitize_description(data.get("description", ""))
    data["vendor_id"] = ObjectId(admin_id)
    data["category_id"] = ObjectId(data.pop("category_id"))
    data["status"] = "active"
    # Assign a stable id to every variant so cart/order code can reference them.
    for variant in data.get("variants", []):
        if not variant.get("id"):
            variant["id"] = uuid.uuid4().hex
    price = data["price"]
    disc  = data.get("discount_percent", 0)
    data["final_price"] = round(price * (1 - disc / 100), 2)
    product_id = await product_model.insert_product(db, data)
    await write_audit_log(
        db, admin_id, "admin", "product_created", "products", product_id,
        {"name": data["name"]}, None,
    )
    return product_id


async def list_products_for_vendor(db, vendor_id: str, limit: int = 50) -> list[dict]:
    items = await product_model.list_products_for_vendor(db, vendor_id, limit)
    return await _enrich_products(db, items)


async def list_products_for_admin(db, limit: int = 50) -> list[dict]:
    items = await product_model.list_products_for_admin(db, limit)
    return await _enrich_products(db, items)


async def update_product(
    db, product_id: str, vendor_id: str, role: str, updates: dict
) -> None:
    existing = await product_model.find_by_id(db, product_id)
    if not existing:
        raise ValueError("NOT_FOUND")
    if role != "admin" and existing.get("vendor_id") != vendor_id:
        raise ValueError("FORBIDDEN")
    if "description" in updates:
        updates["description"] = _sanitize_description(updates["description"])
    # Recompute final_price if price or discount changed
    price = updates.get("price", existing.get("price"))
    disc  = updates.get("discount_percent", existing.get("discount_percent", 0))
    updates["final_price"] = round(price * (1 - disc / 100), 2)
    await product_model.update_product(db, product_id, updates)
    await write_audit_log(
        db, vendor_id, role, "product_updated", "products", product_id, updates, None,
    )
