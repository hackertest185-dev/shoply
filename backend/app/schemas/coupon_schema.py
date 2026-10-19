from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.input_security import ensure_finite


class CouponCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., min_length=3, max_length=32)
    discount_type: Literal["percent", "fixed"] = "percent"
    value: float = Field(..., gt=0)
    min_order_total: float = Field(0, ge=0)
    max_uses: int = Field(0, ge=0, description="0 means unlimited")
    expires_at: datetime | None = None
    active: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Coupon code contains invalid characters")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: float, info):
        ensure_finite(value)
        if info.data.get("discount_type") == "percent" and value > 100:
            raise ValueError("Percent discount cannot exceed 100")
        return round(value, 2)

    @field_validator("min_order_total")
    @classmethod
    def finite_minimum(cls, value: float) -> float:
        return float(ensure_finite(value))


class CouponUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    discount_type: Literal["percent", "fixed"] | None = None
    value: float | None = Field(None, gt=0)
    min_order_total: float | None = Field(None, ge=0)
    max_uses: int | None = Field(None, ge=0)
    expires_at: datetime | None = None
    active: bool | None = None

    @field_validator("value", "min_order_total")
    @classmethod
    def finite_updates(cls, value: float | None) -> float | None:
        return None if value is None else float(ensure_finite(value))


class CouponValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., min_length=3, max_length=32)
    subtotal: float = Field(..., ge=0)

    @field_validator("subtotal")
    @classmethod
    def finite_subtotal(cls, value: float) -> float:
        return float(ensure_finite(value))
