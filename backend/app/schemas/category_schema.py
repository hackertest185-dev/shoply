"""schemas/category_schema.py"""
from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=2, max_length=80)


class CategoryResponse(BaseModel):
    id: str
    name: str
