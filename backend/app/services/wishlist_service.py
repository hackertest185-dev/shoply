"""
services/wishlist_service.py
Business logic for the customer wishlist.
"""
from app.models import wishlist_model
from app.services import products_service


async def list_wishlist_products(db, user_id: str) -> list[dict]:
    product_ids = await wishlist_model.list_item_ids(db, user_id)
    products = []
    for pid in product_ids:
        product = await products_service.get_product(db, pid)
        if product:
            products.append(product)
    return products


async def toggle_wishlist(db, user_id: str, product_id: str) -> dict:
    """Add or remove a product. Returns {action: 'added'|'removed'}."""
    in_wishlist = await wishlist_model.is_in_wishlist(db, user_id, product_id)
    if in_wishlist:
        await wishlist_model.remove_item(db, user_id, product_id)
        return {"action": "removed"}
    added = await wishlist_model.add_item(db, user_id, product_id)
    return {"action": "added" if added else "already"}
