"""schemas/delivery_schema.py  ★"""
from pydantic import BaseModel, ConfigDict, Field


class OTPVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    otp: str = Field(..., pattern=r"^[0-9]{4}$", description="Exactly 4 digits")


class AgentRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rejection_reason: str = Field(..., min_length=10, max_length=500)
