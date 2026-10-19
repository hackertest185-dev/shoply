import pytest
from PIL import Image
from io import BytesIO
from pydantic import ValidationError

from app.core.input_security import (
    clean_text,
    is_allowed_image_url,
    normalize_image,
    validate_pdf,
)
from app.schemas.product_schema import ProductCreate
from app.services.products_service import _parse_sort


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (3, 3), "red").save(output, format="PNG")
    return output.getvalue()


def test_plain_text_removes_control_characters_and_html_tags():
    assert clean_text("  <script>alert(1)</script>\x00 hello  ") == "alert(1) hello"


def test_image_normalization_outputs_metadata_free_webp():
    normalized, mime, extension = normalize_image(_png_bytes())
    assert mime == "image/webp"
    assert extension == "webp"
    assert normalized[:4] == b"RIFF"


def test_pdf_active_content_is_rejected():
    with pytest.raises(ValueError):
        validate_pdf(b"%PDF-1.7 /OpenAction << /JS (alert(1)) >>")


def test_image_url_allowlist_rejects_script_and_unknown_hosts():
    assert not is_allowed_image_url("javascript:alert(1)")
    assert not is_allowed_image_url("https://evil.example/image.png")
    assert is_allowed_image_url("https://images.unsplash.com/photo.png")


def test_product_schema_rejects_svg_and_unknown_image_urls():
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Safe Product",
            description="Plain text",
            price=10,
            category_id="507f1f77bcf86cd799439011",
            images=["data:image/svg+xml;base64,PHN2Zz4="],
        )
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Safe Product",
            description="Plain text",
            price=10,
            category_id="507f1f77bcf86cd799439011",
            images=["https://evil.example/image.png"],
        )


def test_sort_field_is_whitelisted():
    assert _parse_sort("-created_at") == ("created_at", -1)
    assert _parse_sort("password_hash") == ("created_at", 1)
