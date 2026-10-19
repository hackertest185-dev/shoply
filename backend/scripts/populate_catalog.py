"""Populate the local Shoply preview catalog once, preserving legacy orders.

Run inside the backend container after rebuilding the client image:
    python -m scripts.populate_catalog

The generated catalog photos live in client/public/catalog. Prices and stock are
sample content supplied for the preview and must be confirmed before launch.
"""

import asyncio

from bson import ObjectId

from app.core.database import close_db, connect_db, get_db
from app.schemas.product_schema import ProductCreate
from app.services import products_service


LEGACY_PRODUCT_IDS = (
    "69fb3e0267d857c49db9eeb5", "69fb3e2b67d857c49db9eeb7",
    "69fb5789394eb7d300ea1664", "69fb59ef7bad9f5222cbe99c",
    "69fb5a027bad9f5222cbe99e", "69fb61dbc81856f891d38921",
    "69fb709a92342a9861afe4f2", "69fb7114bb9a93bf6327976a",
    "69fb7ea1679f72cf2eb8571c", "69fb7eb1679f72cf2eb8571e",
    "69fb816439078a7768aa8420", "6ad4ff0abc8c1828d23e19b9",
    "6ad502b21a465d8bdd136bb0", "6ad502c31a465d8bdd136bb4",
    "6ad502e81a465d8bdd136bb7",
)

NOTE = "Photos are illustrative. Final details and availability are confirmed on WhatsApp."

PRODUCTS = (
    ("Studio Wireless Headphones", "Electronics", "headphones", 1490, 14,
     "A refined over-ear silhouette for focused listening at home or on the move. The understated charcoal finish keeps the look effortless.", ["audio", "everyday"]),
    ("Compact Bluetooth Speaker", "Electronics", "speaker", 890, 18,
     "A compact speaker with a soft woven look that fits neatly on a shelf, desk, or bedside table. Easy to carry from one room to the next.", ["audio", "portable"]),
    ("Everyday Cognac Tote", "Accessories", "tote", 1290, 12,
     "A roomy, structured tote in a warm cognac tone. A simple shape that works with everyday outfits and keeps essentials close.", ["bag", "everyday"]),
    ("Classic Tan Wristwatch", "Accessories", "watch", 1190, 16,
     "A clean ivory dial and tan strap make this an easy finishing touch for both casual and dressed-up days.", ["watch", "accessory"]),
    ("Sculptural Desk Lamp", "Home Office", "lamp", 1090, 13,
     "A softly glowing desk lamp with a graceful adjustable shape. Designed to bring warmth and focus to your workspace.", ["lighting", "desk"]),
    ("Linen Daily Notebook", "Home Office", "notebook", 290, 24,
     "A calm place for plans, notes, and ideas. Its linen-look cover brings a little texture to the daily desk ritual.", ["stationery", "desk"]),
    ("Ceramic Pour-Over Set", "Kitchen", "pourover", 690, 15,
     "Make your morning coffee feel more considered with a matching pour-over dripper and carafe in a soft ivory finish.", ["coffee", "kitchen"]),
    ("Speckled Stoneware Mug", "Kitchen", "mug", 390, 20,
     "A comfortable everyday mug with a softly speckled finish and a generous handle for slow mornings and afternoon breaks.", ["coffee", "kitchen"]),
    ("Relaxed Cotton Shirt", "Clothing", "shirt", 790, 17,
     "A relaxed button-up in a warm cream shade. Wear it on its own or as an easy layer through the seasons.", ["shirt", "clothing"]),
    ("Everyday Canvas Sneakers", "Clothing", "sneakers", 1090, 14,
     "Clean low-top sneakers in an off-white tone, styled to pair with almost anything in your everyday wardrobe.", ["shoes", "clothing"]),
    ("Sage Yoga Mat", "Fitness", "yoga-mat", 690, 18,
     "A calm sage-colored mat for stretching, yoga, and movement at home. Rolls away neatly when the session is over.", ["yoga", "fitness"]),
    ("Sand Reusable Bottle", "Fitness", "bottle", 490, 22,
     "A minimal reusable bottle in a warm sand shade for your desk, gym bag, or daily commute.", ["bottle", "fitness"]),
)


async def main() -> None:
    await connect_db()
    try:
        db = get_db()
        admin = await db.users.find_one({"role": "admin"}, {"_id": 1})
        if not admin:
            raise RuntimeError("No admin account exists; catalog was not changed.")
        admin_id = str(admin["_id"])
        categories = {c["name"]: str(c["_id"]) for c in await db.categories.find({}, {"name": 1}).to_list(length=100)}
        missing = {item[1] for item in PRODUCTS} - categories.keys()
        if missing:
            raise RuntimeError(f"Missing categories: {sorted(missing)}")

        created = 0
        for name, category, image, price, stock, description, tags in PRODUCTS:
            if await db.products.find_one({"name": name}, {"_id": 1}):
                continue
            body = ProductCreate(
                name=name,
                description=f"{description} {NOTE}",
                price=price,
                category_id=categories[category],
                tags=tags,
                images=[f"/catalog/{image}.webp"],
                variants=[{"sku": f"SHOPLY-{image.upper()}", "stock_qty": stock}],
            )
            await products_service.create_product(db, admin_id, body.model_dump())
            created += 1

        hidden = 0
        for product_id in LEGACY_PRODUCT_IDS:
            existing = await db.products.find_one({"_id": ObjectId(product_id)}, {"status": 1})
            if existing and existing.get("status") == "active":
                await products_service.update_product(db, product_id, admin_id, "admin", {"status": "inactive"})
                hidden += 1

        print(f"Created {created} curated products; hid {hidden} legacy products.")
        print(f"Active catalog total: {await db.products.count_documents({'status': 'active'})}")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
