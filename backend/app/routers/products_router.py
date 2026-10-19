"""routers/products_router.py"""
import base64
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.database import get_db
from app.core.config import settings
from app.core.input_security import normalize_image
from app.core.s3_client import upload_product_image
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.rbac_dependency import require_admin, require_customer
from app.schemas.product_schema import ProductCreate, ProductUpdate, ReviewCreate
from app.services import products_service, review_service

router = APIRouter(prefix="/products", tags=["Products"])


def _ok(data, meta=None) -> dict:
    r = {"success": True, "data": data, "request_id": str(uuid.uuid4())}
    if meta:
        r["meta"] = meta
    return r


@router.get("")
async def list_products(
    request: Request,
    q:            str   | None = Query(None, max_length=100),
    category:     str   | None = None,
    vendor_id:    str   | None = None,
    min_price:    float | None = Query(None, ge=0),
    max_price:    float | None = Query(None, ge=0),
    sort:         str          = Query("-created_at"),
    page:         int          = Query(1, ge=1),
    limit:        int          = Query(20, ge=1, le=100),
    in_stock:     bool         = False,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    params = {k: v for k, v in request.query_params.items()}
    products, total = await products_service.list_products(db, params)
    total_pages = max(1, -(-total // limit))
    return _ok(
        products,
        {"page": page, "limit": limit, "total": total, "total_pages": total_pages},
    )


@router.get("/manage")
async def list_managed_products(
    current_user: dict = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """Admin catalog, including inactive products."""
    items = await products_service.list_products_for_admin(db, limit)
    return _ok(items)


@router.get("/{product_id}")
async def get_product(product_id: str, current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    product = await products_service.get_product(db, product_id)
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "error": {"code": "NOT_FOUND", "message": "Product not found."}},
        )
    return _ok(product)


@router.get("/{product_id}/reviews")
async def list_product_reviews(
    product_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    docs, total = await review_service.list_reviews(db, product_id, page, limit)
    total_pages = max(1, -(-total // limit))
    return _ok(
        docs,
        {"page": page, "limit": limit, "total": total, "total_pages": total_pages},
    )


@router.post("/{product_id}/reviews", status_code=201)
async def create_product_review(
    product_id: str,
    body: ReviewCreate,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    product = await products_service.get_product(db, product_id)
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "error": {"code": "NOT_FOUND", "message": "Product not found."}},
        )
    try:
        review = await review_service.create_review(
            db, product_id, current_user["user_id"], body.rating, body.body
        )
    except ValueError as exc:
        if str(exc) == "REVIEW_EXISTS":
            raise HTTPException(
                status_code=409,
                detail={"code": "REVIEW_EXISTS", "message": "You already reviewed this product."},
            )
        raise HTTPException(status_code=400, detail={"code": str(exc)})
    return _ok(review)


@router.patch("/{product_id}/reviews/me")
async def update_my_review(
    product_id: str,
    body: ReviewCreate,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    try:
        await review_service.update_review(
            db, product_id, current_user["user_id"], body.rating, body.body
        )
    except ValueError as exc:
        if str(exc) == "REVIEW_NOT_FOUND":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        raise HTTPException(status_code=400, detail={"code": str(exc)})
    return _ok({"message": "Review updated."})


@router.delete("/{product_id}/reviews/me")
async def delete_my_review(
    product_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    try:
        await review_service.delete_review(db, product_id, current_user["user_id"])
    except ValueError as exc:
        if str(exc) == "REVIEW_NOT_FOUND":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        raise HTTPException(status_code=400, detail={"code": str(exc)})
    return _ok({"message": "Review deleted."})


@router.post("", status_code=201)
async def create_product(
    body: ProductCreate,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    try:
        product_id = await products_service.create_product(
            db, current_user["user_id"], body.model_dump()
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail={"code": "PRODUCT_NAME_CONFLICT", "message": "A product with this name already exists. Choose a different name."},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc), "message": "Product input is not safe."})
    return _ok({
        "id":      product_id,
        "status":  "active",
        "message": "Product is available in the shop.",
    })


@router.patch("/{product_id}")
async def update_product(
    product_id: str,
    body: ProductUpdate,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    try:
        await products_service.update_product(
            db, product_id, current_user["user_id"],
            current_user["role"], body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        code = str(exc)
        if code == "NOT_FOUND":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        if code in {"UNSAFE_IMAGE_URL", "INVALID_PRICE"}:
            raise HTTPException(status_code=422, detail={"code": code, "message": "Product input is not safe."})
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
    return _ok({"message": "Product updated."})


@router.post("/images", status_code=201)
async def upload_product_image_endpoint(
    image: UploadFile = File(..., description="JPEG, PNG, or WebP image; max 6MB"),
    current_user: dict = Depends(require_admin),
):
    """Validate and normalize a product image before it enters product data.

    The returned data URL is safe, metadata-free WebP.  Deployments with an
    object store can replace this response with a private upload service
    without changing the validation contract.
    """
    content = await image.read(settings.PRODUCT_IMAGE_MAX_BYTES + 1)
    if len(content) > settings.PRODUCT_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail={"code": "FILE_TOO_LARGE"})
    try:
        normalized, mime, _ = normalize_image(content)
    except ValueError:
        raise HTTPException(status_code=415, detail={"code": "UNSUPPORTED_FILE", "message": "Only valid JPEG, PNG, and WebP images are allowed."})
    image_value = f"data:{mime};base64,{base64.b64encode(normalized).decode('ascii')}"
    if settings.AWS_ACCESS_KEY_ID.strip() and settings.AWS_SECRET_ACCESS_KEY.strip() and settings.S3_BUCKET_PRODUCTS.strip():
        try:
            image_value = await upload_product_image(current_user["user_id"], normalized, "product.webp")
        except Exception:
            raise HTTPException(status_code=503, detail={"code": "IMAGE_STORAGE_UNAVAILABLE", "message": "Image storage is temporarily unavailable."})
    return _ok({
        "image": image_value,
        "content_type": mime,
        "size": len(normalized),
    })


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    # Soft delete
    try:
        await products_service.update_product(
            db, product_id, current_user["user_id"],
            current_user["role"], {"status": "inactive"},
        )
    except ValueError as exc:
        code = str(exc)
        if code == "NOT_FOUND":
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
    return _ok({"message": "Product removed."})
