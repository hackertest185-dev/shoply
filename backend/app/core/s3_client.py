"""
core/s3_client.py
Boto3 S3 helpers. All delivery docs stored private (never public).
Signed URLs generated per-request with short TTL (15 min).
"""
import mimetypes
import uuid
from datetime import datetime, timezone
from io import BytesIO

import boto3

from .config import settings

_s3_client = None


def get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _s3_client


ALLOWED_DOCUMENT_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
ALLOWED_PROOF_MIME_TYPES = {"image/jpeg", "image/png"}
ALLOWED_PRODUCT_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _detect_mime(content: bytes, filename: str) -> str:
    """Server-side MIME detection — never trust client Content-Type."""
    # Magic bytes detection
    if content[:4] == b"%PDF":
        return "application/pdf"
    if content[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:4] in (b"RIFF", b"WEBP"):
        return "image/webp"
    # Fallback to extension
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


async def upload_delivery_document(
    user_id: str,
    document_type: str,
    submission_round: int,
    content: bytes,
    filename: str,
) -> str:
    """
    Upload a verification document to the private delivery-docs bucket.
    Returns the S3 object key (not a public URL — use generate_signed_url to access).
    Path: {user_id}/{submission_round}/{document_type}/{uuid}.{ext}
    """
    mime = _detect_mime(content, filename)
    if mime not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise ValueError(f"File type {mime} not allowed for documents")

    ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[mime]
    key = f"{user_id}/{submission_round}/{document_type}/{uuid.uuid4()}.{ext}"

    get_s3().put_object(
        Bucket=settings.S3_BUCKET_DELIVERY_DOCS,
        Key=key,
        Body=BytesIO(content),
        ContentType=mime,
        ServerSideEncryption="AES256",
        Tagging=f"user_id={user_id}&document_type={document_type}&round={submission_round}",
    )
    return key


async def upload_proof_of_delivery(
    order_id: str,
    agent_id: str,
    content: bytes,
    filename: str,
) -> str:
    """
    Upload proof-of-delivery image. Immutable path — no overwrite.
    Returns full S3 URL (stored in order record; not signed — internal ref only).
    """
    mime = _detect_mime(content, filename)
    if mime not in ALLOWED_PROOF_MIME_TYPES:
        raise ValueError(f"File type {mime} not allowed for proof images")

    ext = "jpg" if mime == "image/jpeg" else "png"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    key = f"{order_id}/{ts}_{uuid.uuid4()}.{ext}"

    get_s3().put_object(
        Bucket=settings.S3_BUCKET_PROOF,
        Key=key,
        Body=BytesIO(content),
        ContentType=mime,
        ServerSideEncryption="AES256",
        Tagging=f"order_id={order_id}&agent_id={agent_id}",
    )

    return f"https://{settings.S3_BUCKET_PROOF}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"


def generate_signed_url(bucket: str, key: str, expiry_seconds: int = 900) -> str:
    """Generate a pre-signed URL valid for expiry_seconds (default 15 min)."""
    return get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiry_seconds,
    )


async def upload_product_image(
    vendor_id: str,
    content: bytes,
    filename: str,
) -> str:
    """Upload a product image to the public products bucket. Returns public URL."""
    mime = _detect_mime(content, filename)
    if mime not in ALLOWED_PRODUCT_MIME_TYPES:
        raise ValueError(f"File type {mime} not allowed for product images")

    ext = mime.split("/")[-1].replace("jpeg", "jpg")
    key = f"{vendor_id}/{uuid.uuid4()}.{ext}"

    get_s3().put_object(
        Bucket=settings.S3_BUCKET_PRODUCTS,
        Key=key,
        Body=BytesIO(content),
        ContentType=mime,
        ACL="public-read",
    )

    return f"https://{settings.S3_BUCKET_PRODUCTS}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
