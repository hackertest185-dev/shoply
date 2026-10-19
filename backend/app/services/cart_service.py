"""services/cart_service.py"""
from app.models import cart_model, product_model


async def get_cart_with_prices(db, user_id: str) -> dict:
    """
    Fetch cart and enrich each item with real-time pricing and stock.
    Prices are NEVER stored in the cart — always recalculated from products.
    """
    cart_doc = await cart_model.get_cart(db, user_id)
    items = cart_doc.get("items", []) if cart_doc else []

    enriched = []
    warnings = []
    subtotal = 0.0

    for item in items:
        product = await product_model.find_by_id(db, item["product_id"])
        if not product or product.get("status") != "active":
            warnings.append({
                "product_id": item["product_id"],
                "type": "UNAVAILABLE",
                "message": f"'{item.get('name', 'Item')}' is no longer available.",
            })
            continue

        unit_price = product["final_price"]
        qty = item["qty"]
        item_subtotal = round(unit_price * qty, 2)
        subtotal += item_subtotal

        # Find variant stock
        variants = product.get("variants", [])
        variant = next(
            (v for v in variants if str(v.get("id")) == item.get("variant_id")), None
        ) if item.get("variant_id") else (variants[0] if variants else None)

        if variants:
            stock_available = variant.get("stock_qty", 0) if variant else 0
            in_stock = stock_available >= qty
            if not in_stock:
                warnings.append({
                    "product_id": item["product_id"],
                    "type": "LOW_STOCK",
                    "message": f"Only {stock_available} left in stock for '{product['name']}'.",
                })
        else:
            # Product has no variants — stock is not tracked, always available.
            stock_available = None
            in_stock = True

        enriched.append({
            "product_id":     item["product_id"],
            "variant_id":     item.get("variant_id"),
            "name":           product["name"],
            "variant_label":  f"{variant['color'] or ''} {variant.get('size') or ''}".strip() if variant else None,
            "qty":            qty,
            "unit_price":     unit_price,
            "subtotal":       item_subtotal,
            "in_stock":       in_stock,
            "stock_available": stock_available,
            "image":          product.get("images")[0] if product.get("images") else None,
        })

    # WhatsApp orders quote the listed product prices. No unconfigured tax is added.
    tax = 0.0
    total = round(subtotal, 2)

    return {
        "items": enriched,
        "summary": {
            "item_count":   sum(i["qty"] for i in enriched),
            "subtotal":     round(subtotal, 2),
            "tax_estimate": tax,
            "total":        total,
        },
        "warnings": warnings,
    }


async def add_item(db, user_id: str, product_id: str, variant_id: str | None, qty: int) -> dict:
    product = await product_model.find_by_id(db, product_id)
    if not product or product.get("status") != "active":
        raise ValueError("PRODUCT_NOT_FOUND")

    # Resolve the concrete variant (server-generated id) and validate stock.
    variants = product.get("variants", [])
    resolved_variant_id: str | None = None
    if variants:
        variant = next(
            (v for v in variants if str(v.get("id")) == variant_id), None
        ) if variant_id else variants[0]
        if not variant:
            raise ValueError("VARIANT_NOT_FOUND")
        if variant.get("stock_qty", 0) < qty:
            raise ValueError("INSUFFICIENT_STOCK")
        resolved_variant_id = variant.get("id")

    cart_doc = await cart_model.get_cart(db, user_id)
    items = cart_doc.get("items", []) if cart_doc else []

    existing = next(
        (i for i in items if i["product_id"] == product_id and i.get("variant_id") == resolved_variant_id),
        None,
    )
    if existing:
        existing["qty"] = min(99, existing["qty"] + qty)
    else:
        items.append({"product_id": product_id, "variant_id": resolved_variant_id, "qty": qty})

    await cart_model.upsert_cart(db, user_id, items)
    return await get_cart_with_prices(db, user_id)


async def update_item(db, user_id: str, product_id: str, variant_id: str | None, qty: int) -> dict:
    cart_doc = await cart_model.get_cart(db, user_id)
    if not cart_doc:
        raise ValueError("CART_EMPTY")
    items = cart_doc.get("items", [])
    for item in items:
        if item["product_id"] == product_id and item.get("variant_id") == variant_id:
            item["qty"] = qty
            break
    await cart_model.upsert_cart(db, user_id, items)
    return await get_cart_with_prices(db, user_id)


async def remove_item(db, user_id: str, product_id: str) -> dict:
    cart_doc = await cart_model.get_cart(db, user_id)
    if not cart_doc:
        return await get_cart_with_prices(db, user_id)
    items = [i for i in cart_doc.get("items", []) if i["product_id"] != product_id]
    await cart_model.upsert_cart(db, user_id, items)
    return await get_cart_with_prices(db, user_id)


async def clear_cart(db, user_id: str) -> None:
    await cart_model.clear_cart(db, user_id)
