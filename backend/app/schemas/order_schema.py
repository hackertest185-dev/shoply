"""schemas/order_schema.py"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.input_security import clean_text


class AddressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label:      str | None = None
    line1:      str
    line2:      str | None = None
    city:       str
    state:      str
    zip_code:   str
    country:    str
    is_default: bool = False

    @field_validator("label", "line1", "line2", "city", "state", "zip_code", "country")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, max_length=200)


class CheckoutIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_id:      str
    billing_same:    bool = True
    billing_address: AddressCreate | None = None


class OrderConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_intent_id: str
    address_id:        str


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whatsapp_number: str = Field(..., pattern=r"^\+[1-9]\d{7,14}$", description="WhatsApp number in international format, for example +201234567890")
    coupon_code: str | None = Field(default=None, min_length=3, max_length=32)


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class AddressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label:      str | None = None
    line1:      str | None = None
    line2:      str | None = None
    city:       str | None = None
    state:      str | None = None
    zip_code:   str | None = None
    country:    str | None = None
    is_default: bool | None = None

    @field_validator("label", "line1", "line2", "city", "state", "zip_code", "country")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, max_length=200)
