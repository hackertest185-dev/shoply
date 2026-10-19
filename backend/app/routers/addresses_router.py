"""
routers/addresses_router.py
Customer address book — CRUD + default selection.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db
from app.dependencies.rbac_dependency import require_customer
from app.models import address_model
from app.schemas.order_schema import AddressCreate, AddressUpdate

router = APIRouter(prefix="/addresses", tags=["Addresses"])


def _ok(data, meta=None):
    r = {"success": True, "data": data, "request_id": str(uuid.uuid4())}
    if meta:
        r["meta"] = meta
    return r


@router.get("")
async def list_addresses(
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    items = await address_model.list_addresses(db, current_user["user_id"])
    return _ok(items)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_address(
    body: AddressCreate,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    address_id = await address_model.insert_address(db, current_user["user_id"], body.model_dump())
    return _ok({"id": address_id})


@router.get("/{address_id}")
async def get_address(
    address_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    addr = await address_model.get_address(db, address_id, current_user["user_id"])
    if not addr:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok(addr)


@router.patch("/{address_id}")
async def update_address(
    address_id: str,
    body: AddressUpdate,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail={"code": "NO_CHANGES"})
    updated = await address_model.update_address(db, address_id, current_user["user_id"], updates)
    if not updated:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok({"message": "Address updated."})


@router.delete("/{address_id}")
async def delete_address(
    address_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    deleted = await address_model.delete_address(db, address_id, current_user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok({"message": "Address deleted."})


@router.post("/{address_id}/set-default")
async def set_default_address(
    address_id: str,
    current_user: dict = Depends(require_customer),
    db=Depends(get_db),
):
    addr = await address_model.get_address(db, address_id, current_user["user_id"])
    if not addr:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    updated = await address_model.update_address(
        db, address_id, current_user["user_id"], {"is_default": True}
    )
    if not updated:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return _ok({"message": "Default address updated."})
