"""routers/categories_router.py"""
import uuid
from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.models.category_model import list_categories

router = APIRouter(prefix="/categories", tags=["Categories"])


def _ok(data) -> dict:
    return {"success": True, "data": data, "request_id": str(uuid.uuid4())}


@router.get("")
async def categories(db=Depends(get_db)):
    return _ok(await list_categories(db))
