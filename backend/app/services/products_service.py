"""services/products_service.py"""
import base64
import math
import uuid
from bson import ObjectId

from app.core.input_security import clean_text, decode_data_image, is_allowed_image_url, normalize_image
from app.models import product_model
from app.services.audit_log_service import write_audit_log

def _sanitize_description(raw: str) -> str:
    # Descriptions are rendered as React text.  Keeping them plain text avoids
    # needing a second HTML sanitizer in every frontend surface.
    return clean_text(raw, max_length=10_000)


def _normalize_images(images: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in images or []:
        value = str(raw).strip()
        if value.startswith("data:"):
            content, _ = decode_data_image(value)
            encoded, mime, _ = normalize_image(content)
            normalized.append(f"data:{mime};base64,{base64.b64encode(encoded).decode('ascii')}")
        elif is_allowed_image_url(value):
            normalized.append(value)
        else:
            raise ValueError("UNSAFE_IMAGE_URL")
    return normalized


def _build_filters(params: dict) -> dict:
    """Build a safe MongoDB filter dict from query parameters."""
    filters: dict = {"status": {"$eq": "active"}}

    if q := params.get("q"):
        # Text search — uses the text index; sanitized by $text operator
        filters["$text"] = {"$search": clean_text(str(q), max_length=100)}

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
    allowed = {"created_at", "updated_at", "name", "final_price", "price", "ratings.average"}
    descending = sort_str.startswith("-")
    field = sort_str[1:] if descending else sort_str
    return (field if field in allowed else "created_at", -1 if descending else 1)


async def list_products(db, params: dict) -> tuple[list[dict], int]:
    try:
        page = max(1, int(params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = min(100, max(1, int(params.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
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
    if not math.isfinite(float(data.get("price", 0))):
        raise ValueError("INVALID_PRICE")
    data["description"] = _sanitize_description(data.get("description", ""))
    data["name"] = clean_text(data.get("name", ""), max_length=200)
    data["tags"] = [clean_text(tag, max_length=30) for tag in data.get("tags", [])]
    data["images"] = _normalize_images(data.get("images", []))
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
    if "name" in updates:
        updates["name"] = clean_text(updates["name"], max_length=200)
    if "tags" in updates:
        updates["tags"] = [clean_text(tag, max_length=30) for tag in updates["tags"]]
    if "images" in updates:
        updates["images"] = _normalize_images(updates["images"])
    # Recompute final_price if price or discount changed
    price = updates.get("price", existing.get("price"))
    disc  = updates.get("discount_percent", existing.get("discount_percent", 0))
    if not math.isfinite(float(price)) or not math.isfinite(float(disc)):
        raise ValueError("INVALID_PRICE")
    updates["final_price"] = round(price * (1 - disc / 100), 2)
    await product_model.update_product(db, product_id, updates)
    await write_audit_log(
        db, vendor_id, role, "product_updated", "products", product_id, updates, None,
    )
