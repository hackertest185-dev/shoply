"""schemas/cart_schema.py"""
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CartItemAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    variant_id: str | None = None
    qty:        int = Field(..., ge=1, le=99)

    @field_validator("product_id")
    @classmethod
    def product_id_must_be_object_id(cls, v: str) -> str:
        # Fail fast with 422 instead of causing a 500 later.
        ObjectId(v)
        return v


class CartItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    qty:        int = Field(..., ge=1, le=99)
    variant_id: str | None = None
