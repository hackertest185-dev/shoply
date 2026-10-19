"""schemas/product_schema.py"""
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.input_security import clean_text, ensure_finite, is_allowed_image_url


def _validate_images(value: list[str]) -> list[str]:
    """Keep inline uploads bounded so a single product cannot exhaust MongoDB."""
    for image in value:
        if len(image) > 6_000_000:
            raise ValueError("Each product image must be smaller than 6 MB.")
        if image.startswith("data:") and not image.startswith(
            ("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")
        ):
            raise ValueError("Only JPEG, PNG, and WebP images are supported.")
        if image.startswith("data:"):
            # Data images are accepted for backwards compatibility, but are
            # decoded and re-encoded by the service before persistence.
            continue
        if not is_allowed_image_url(image):
            raise ValueError("Image URL is not from an approved HTTPS host.")
    return value


class ProductStatus(str, Enum):
    DRAFT          = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE         = "active"
    INACTIVE       = "inactive"


class VariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id:        str | None = Field(None, max_length=64)  # server-generated when omitted
    color:     str | None = Field(None, max_length=50)
    size:      str | None = Field(None, max_length=50)
    sku:       str        = Field(..., min_length=1, max_length=50)
    stock_qty: int        = Field(..., ge=0)


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name:             str                     = Field(..., min_length=3, max_length=200)
    description:      str                     = Field(..., max_length=10_000)
    price:            float                   = Field(..., gt=0.0, le=999_999.99)
    discount_percent: Annotated[int, Field(ge=0, le=90)] = 0
    category_id:      str
    tags:             list[str]               = Field(default=[], max_length=20)
    variants:         list[VariantCreate]     = Field(default=[])
    images:           list[str]               = Field(default=[], max_length=8)
    status:           ProductStatus           = ProductStatus.ACTIVE

    _validate_image_values = field_validator("images")(_validate_images)

    @field_validator("price")
    @classmethod
    def price_must_be_finite(cls, value: float) -> float:
        return float(ensure_finite(value))

    @field_validator("name", "description")
    @classmethod
    def plain_text_fields(cls, value: str) -> str:
        return clean_text(value)

    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return [t[:30] for t in v]  # cap tag length


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name:             str | None   = Field(None, min_length=3, max_length=200)
    description:      str | None   = Field(None, max_length=10_000)
    price:            float | None = Field(None, gt=0.0, le=999_999.99)
    discount_percent: int | None   = Field(None, ge=0, le=90)
    tags:             list[str] | None = None
    images:           list[str] | None = Field(None, max_length=8)
    status:           ProductStatus | None = None

    _validate_image_values = field_validator("images")(_validate_images)

    @field_validator("price")
    @classmethod
    def price_must_be_finite(cls, value: float | None) -> float | None:
        return None if value is None else float(ensure_finite(value))

    @field_validator("name", "description")
    @classmethod
    def plain_text_fields(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value)


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(..., ge=1, le=5)
    body:   str = Field(..., min_length=10, max_length=2000)

    @field_validator("body")
    @classmethod
    def plain_text_body(cls, value: str) -> str:
        value = clean_text(value, max_length=2000)
        if len(value) < 10:
            raise ValueError("Review is too short")
        return value
