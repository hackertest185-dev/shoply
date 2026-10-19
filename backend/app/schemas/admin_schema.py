"""schemas/admin_schema.py"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ProductRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=5, max_length=500)


class RefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cents: int = Field(..., ge=1)
    reason:       str = Field(..., min_length=5, max_length=500)


class OrderAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delivery_id: str = Field(..., min_length=1, description="User ID of the delivery agent")


class CompleteDeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_received: Literal[True] = Field(
        ..., description="The admin confirms that the InstaPay payment was received."
    )
