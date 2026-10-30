"""
services/review_service.py
Business logic for product reviews.
"""
from app.models import review_model
from app.services.audit_log_service import write_audit_log


async def list_reviews(db, product_id: str, page: int = 1, limit: int = 20) -> tuple[list[dict], int]:
    return await review_model.list_reviews(db, product_id, page, limit)


async def create_review(db, product_id: str, customer_id: str, rating: int, body: str) -> dict:
    existing = await review_model.get_review(db, product_id, customer_id)
    if existing:
        raise ValueError("REVIEW_EXISTS")
    review = await review_model.create_review(db, product_id, customer_id, rating, body)
    await write_audit_log(
        db, customer_id, "customer", "review_created", "reviews", review["id"],
        {"product_id": product_id, "rating": rating}, None,
    )
    return review


async def update_review(db, product_id: str, customer_id: str, rating: int, body: str) -> None:
    existing = await review_model.get_review(db, product_id, customer_id)
    if not existing:
        raise ValueError("REVIEW_NOT_FOUND")
    await review_model.update_review(db, product_id, customer_id, rating, body)
    await write_audit_log(
        db, customer_id, "customer", "review_updated", "reviews",
        existing["id"], {"product_id": product_id, "rating": rating}, None,
    )


async def delete_review(db, product_id: str, customer_id: str) -> None:
    existing = await review_model.get_review(db, product_id, customer_id)
    if not existing:
        raise ValueError("REVIEW_NOT_FOUND")
    await review_model.delete_review(db, product_id, customer_id)
    await write_audit_log(
        db, customer_id, "customer", "review_deleted", "reviews", existing["id"],
        {"product_id": product_id}, None,
    )
