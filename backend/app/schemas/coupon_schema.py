from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        if info.data.get("discount_type") == "percent" and value > 100:
            raise ValueError("Percent discount cannot exceed 100")
        return round(value, 2)


class CouponUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    discount_type: Literal["percent", "fixed"] | None = None
    value: float | None = Field(None, gt=0)
    min_order_total: float | None = Field(None, ge=0)
    max_uses: int | None = Field(None, ge=0)
    expires_at: datetime | None = None
    active: bool | None = None


class CouponValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., min_length=3, max_length=32)
    subtotal: float = Field(..., ge=0)
