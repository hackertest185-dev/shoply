import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.routers.wishlist_router import list_wishlist


@pytest.mark.asyncio
async def test_empty_wishlist_can_be_listed_without_a_product_id():
    db = AsyncMongoMockClient().shoply_test
    result = await list_wishlist(current_user={"user_id": str(ObjectId())}, db=db)
    assert result["success"] is True
    assert result["data"] == []
