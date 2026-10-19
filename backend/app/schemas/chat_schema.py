from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.input_security import clean_text


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def plain_text_only(cls, value: str) -> str:
        value = clean_text(value, max_length=2000)
        if not value:
            raise ValueError("Message cannot be empty")
        return value
