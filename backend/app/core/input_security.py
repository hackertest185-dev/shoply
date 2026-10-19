"""Shared input and upload security helpers.

User supplied strings are treated as data throughout the API.  This module
keeps the rules in one place so new routes do not accidentally re-introduce
HTML, unsafe URLs, Mongo operators, or unbounded numeric values.
"""
from __future__ import annotations

import base64
import binascii
import math
import re
from io import BytesIO
from urllib.parse import urlparse

import bleach
from PIL import Image, UnidentifiedImageError


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MONGO_OPERATOR = re.compile(r"(^\$|\.)")
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_HOSTS = {
    "images.unsplash.com",
}


def clean_text(value: str, *, max_length: int | None = None) -> str:
    """Return normalized plain text with control characters removed."""
    # Store plain text only.  React escaping remains the final rendering
    # safeguard, while stripping tags here prevents unsafe HTML from being
    # reintroduced by a future consumer or export path.
    value = bleach.clean(str(value), tags=[], attributes={}, strip=True)
    value = _CONTROL_CHARS.sub("", value).strip()
    if max_length is not None:
        value = value[:max_length]
    return value


def ensure_finite(value: float | int) -> float | int:
    """Reject NaN and infinity before they reach MongoDB or calculations."""
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError("Value must be finite")
    return value


def assert_safe_mongo_keys(value: object) -> None:
    """Reject nested user dictionaries containing Mongo operators."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if _MONGO_OPERATOR.search(str(key)):
                raise ValueError("Mongo operators are not allowed")
            assert_safe_mongo_keys(nested)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_safe_mongo_keys(item)


def is_allowed_image_url(value: str, allowed_hosts: set[str] | None = None) -> bool:
    """Allow only relative assets or explicit HTTPS image hosts."""
    raw = str(value).strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return True
    parsed = urlparse(raw)
    hosts = set(allowed_hosts or ALLOWED_IMAGE_HOSTS)
    # Add only the configured product bucket, never arbitrary S3 buckets.
    try:
        from .config import settings
        bucket = str(settings.S3_BUCKET_PRODUCTS).strip()
        region = str(settings.AWS_REGION).strip()
        if bucket and region:
            hosts.update({
                f"{bucket}.s3.amazonaws.com",
                f"{bucket}.s3.{region}.amazonaws.com",
            })
    except Exception:
        pass
    return parsed.scheme == "https" and parsed.hostname in hosts


def decode_data_image(data_url: str, *, max_bytes: int = 6 * 1024 * 1024) -> tuple[bytes, str]:
    """Decode a data URL and require an allowed image MIME type."""
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise ValueError("Only base64 image data is supported")
    header, encoded = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0].lower()
    if mime not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError("Only JPEG, PNG, and WebP images are supported")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid image data") from exc
    if not content or len(content) > max_bytes:
        raise ValueError("Image is empty or too large")
    return content, mime


def normalize_image(content: bytes, *, max_bytes: int = 6 * 1024 * 1024) -> tuple[bytes, str, str]:
    """Decode and re-encode an image, stripping metadata and active payloads."""
    if len(content) == 0 or len(content) > max_bytes:
        raise ValueError("Image is empty or too large")
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Only JPEG, PNG, and WebP images are supported")
            width, height = source.size
            if width < 1 or height < 1 or width > 8000 or height > 8000 or width * height > 25_000_000:
                raise ValueError("Image dimensions are not allowed")
            # Convert through RGB/RGBA and save without EXIF/ICC/animation.
            image = source.convert("RGBA" if "A" in source.getbands() else "RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Invalid image file") from exc
    normalized = output.getvalue()
    if len(normalized) > max_bytes:
        raise ValueError("Normalized image is too large")
    return normalized, "image/webp", "webp"


def validate_pdf(content: bytes, *, max_bytes: int = 10 * 1024 * 1024) -> bytes:
    """Reject obvious active PDF features before private storage.

    The file remains an attachment and is never rendered inline.  A later
    sanitizer can add deeper PDF rewriting without changing this API.
    """
    if len(content) == 0 or len(content) > max_bytes or not content.startswith(b"%PDF"):
        raise ValueError("Invalid PDF file")
    lowered = content.lower()
    for marker in (b"/javascript", b"/js", b"/openaction", b"/aa", b"/embeddedfile"):
        if marker in lowered:
            raise ValueError("PDF contains active content")
    return content
